import type { Message } from "@alfred/protocol";
import { validateMessage } from "./validator";

export type ConnectionPhase =
  | "idle"
  | "connecting"
  | "handshaking"
  | "ready"
  | "reconnecting"
  | "closed"
  | "error";

export interface ServerInfo {
  serverName: string;
  serverVersion: string;
  sessionId: string;
  protocolVersion: number;
}

export interface PhaseEvent {
  phase: ConnectionPhase;
  server?: ServerInfo;
  error?: string;
}

export interface WireEntry {
  entryId: string;
  direction: "in" | "out";
  type: string;
  raw: unknown;
  valid: boolean;
  errors?: string;
  at: string;
}

export interface ProtocolClientOptions {
  url: string;
  clientName?: string;
  clientVersion?: string;
  protocolVersion?: number;
  WebSocketCtor?: { new (url: string): WebSocket };
  reconnect?: boolean;
  backoffBaseMs?: number;
  backoffMaxMs?: number;
}

interface EventMap {
  phase: (e: PhaseEvent) => void;
  message: (m: Message) => void;
  wire: (w: WireEntry) => void;
}

export class ProtocolClient {
  protected ws: WebSocket | null = null;
  private phase: ConnectionPhase = "idle";
  private counter = 0;
  private readonly handlers: { [K in keyof EventMap]: Set<EventMap[K]> } = {
    phase: new Set(),
    message: new Set(),
    wire: new Set(),
  };

  protected readonly url: string;
  protected readonly clientName: string;
  protected readonly clientVersion: string;
  protected readonly protocolVersion: number;
  protected readonly WebSocketCtor: { new (url: string): WebSocket };
  protected readonly reconnect: boolean;
  protected readonly backoffBaseMs: number;
  protected readonly backoffMaxMs: number;

  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manuallyClosed = false;

  constructor(options: ProtocolClientOptions) {
    this.url = options.url;
    this.clientName = options.clientName ?? "alfred-desktop-ui";
    this.clientVersion = options.clientVersion ?? "0.1.0";
    this.protocolVersion = options.protocolVersion ?? 1;
    this.WebSocketCtor = options.WebSocketCtor ?? WebSocket;
    this.reconnect = options.reconnect ?? true;
    this.backoffBaseMs = options.backoffBaseMs ?? 500;
    this.backoffMaxMs = options.backoffMaxMs ?? 8000;
  }

  private uid(prefix: string): string {
    this.counter += 1;
    return `${prefix}-${this.counter}-${Math.floor(Math.random() * 1_000_000)}`;
  }

  on<K extends keyof EventMap>(event: K, handler: EventMap[K]): () => void {
    this.handlers[event].add(handler);
    return () => {
      this.handlers[event].delete(handler);
    };
  }

  protected emit<K extends keyof EventMap>(
    event: K,
    ...args: Parameters<EventMap[K]>
  ): void {
    for (const h of this.handlers[event]) {
      (h as (...a: Parameters<EventMap[K]>) => void)(...args);
    }
  }

  getPhase(): ConnectionPhase {
    return this.phase;
  }

  protected setPhase(phase: ConnectionPhase, extra: Omit<PhaseEvent, "phase"> = {}): void {
    this.phase = phase;
    this.emit("phase", { phase, ...extra });
  }

  connect(): void {
    this.manuallyClosed = false;
    this.reconnectAttempts = 0;
    this.openSocket("connecting");
  }

  protected openSocket(initialPhase: ConnectionPhase): void {
    this.setPhase(initialPhase);
    const ws = new this.WebSocketCtor(this.url);
    this.ws = ws;
    ws.onopen = () => this.onOpen();
    ws.onmessage = (ev: MessageEvent) => this.handleInbound(ev.data);
    ws.onerror = () => this.setPhase("error", { error: "socket error" });
    ws.onclose = () => this.onClose();
  }

  protected onOpen(): void {
    this.setPhase("handshaking");
    this.sendMessage({
      ...this.envelope(),
      type: "client.hello",
      client_name: this.clientName,
      client_version: this.clientVersion,
      protocol_version: this.protocolVersion,
    });
  }

  protected onClose(): void {
    this.ws = null;
    if (this.manuallyClosed || !this.reconnect) {
      this.setPhase("closed");
      return;
    }
    const delay = Math.min(
      this.backoffMaxMs,
      this.backoffBaseMs * 2 ** this.reconnectAttempts,
    );
    this.reconnectAttempts += 1;
    this.setPhase("reconnecting");
    this.reconnectTimer = setTimeout(() => this.openSocket("reconnecting"), delay);
  }

  protected handleInbound(data: unknown): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(typeof data === "string" ? data : String(data));
    } catch {
      this.logWire("in", "?", data, { valid: false, errors: "invalid JSON" });
      this.setPhase("error", { error: "received a non-JSON frame" });
      return;
    }
    const result = validateMessage(parsed);
    const type = (parsed as { type?: string }).type ?? "?";
    this.logWire("in", type, parsed, result);
    if (!result.valid) {
      this.setPhase("error", { error: `invalid inbound ${type}: ${result.errors}` });
      return;
    }
    const msg = parsed as Message;
    this.onValidMessage(msg);
    this.emit("message", msg);
  }

  protected onValidMessage(msg: Message): void {
    if (msg.type === "server.hello") {
      this.reconnectAttempts = 0;
      this.setPhase("ready", {
        server: {
          serverName: msg.server_name,
          serverVersion: msg.server_version,
          sessionId: msg.session_id,
          protocolVersion: msg.protocol_version,
        },
      });
    } else if (msg.type === "error" && msg.code === "unsupported_version") {
      this.setPhase("error", { error: msg.message });
    }
  }

  disconnect(): void {
    this.manuallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
  }

  submitCommand(text: string, opts: { scopeOverride?: string } = {}): string {
    const msg: Message = {
      ...this.envelope(),
      type: "command.submit",
      text,
      channel: "desktop",
      ...(opts.scopeOverride ? { scope_override: opts.scopeOverride } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }

  activateKillSwitch(reason?: string): string {
    const msg: Message = {
      ...this.envelope(),
      type: "kill_switch.activate",
      channel: "desktop",
      ...(reason ? { reason } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }

  requestMemoryList(status?: "provisional" | "confirmed"): string {
    const msg: Message = {
      ...this.envelope(),
      type: "memory.list_request",
      ...(status ? { status } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }

  editMemory(memId: string, patch: { status?: "provisional" | "confirmed"; tags?: string[] }): string {
    const msg: Message = {
      ...this.envelope(),
      type: "memory.edit",
      mem_id: memId,
      ...(patch.status ? { status: patch.status } : {}),
      ...(patch.tags ? { tags: patch.tags } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }

  deleteMemory(memId: string): string {
    const msg: Message = { ...this.envelope(), type: "memory.delete", mem_id: memId };
    this.sendMessage(msg);
    return msg.id;
  }

  protected envelope(): { v: 1; id: string; ts: string } {
    return { v: 1, id: this.uid("ui"), ts: new Date().toISOString() };
  }

  protected sendMessage(msg: Message): void {
    const result = validateMessage(msg);
    this.logWire("out", msg.type, msg, result);
    this.ws?.send(JSON.stringify(msg));
  }

  protected logWire(
    direction: "in" | "out",
    type: string,
    raw: unknown,
    result: { valid: boolean; errors?: string },
  ): void {
    this.emit("wire", {
      entryId: this.uid("wire"),
      direction,
      type,
      raw,
      valid: result.valid,
      errors: result.errors,
      at: new Date().toISOString(),
    });
  }
}

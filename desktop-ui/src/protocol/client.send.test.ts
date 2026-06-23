import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { ProtocolClient } from "./client";
import { FakeWebSocket, lastSocket, resetSockets } from "../test/fake-websocket";

const Ctor = FakeWebSocket as unknown as { new (url: string): WebSocket };
const serverHello = {
  v: 1, id: "s-1", ts: "2026-06-23T00:00:00Z", type: "server.hello",
  corr: "ui-1-0", server_name: "m", server_version: "0.1.0",
  protocol_version: 1, session_id: "sess",
};

describe("ProtocolClient send helpers", () => {
  beforeEach(() => resetSockets());

  it("submitCommand emits a valid command.submit and returns its id", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: false });
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive(serverHello);
    const id = client.submitCommand("check the build", { scopeOverride: "coding" });
    const sent = JSON.parse(ws.sent.at(-1)!);
    expect(sent.type).toBe("command.submit");
    expect(sent.id).toBe(id);
    expect(sent.channel).toBe("desktop");
    expect(sent.text).toBe("check the build");
    expect(sent.scope_override).toBe("coding");
  });

  it("omits scope_override when absent (never null)", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: false });
    client.connect();
    const ws = lastSocket();
    ws.open();
    client.submitCommand("hello");
    const sent = JSON.parse(ws.sent.at(-1)!);
    expect("scope_override" in sent).toBe(false);
  });

  it("activateKillSwitch emits a valid kill_switch.activate", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: false });
    client.connect();
    const ws = lastSocket();
    ws.open();
    client.activateKillSwitch("panic");
    const sent = JSON.parse(ws.sent.at(-1)!);
    expect(sent.type).toBe("kill_switch.activate");
    expect(sent.channel).toBe("desktop");
    expect(sent.reason).toBe("panic");
  });
});

describe("ProtocolClient reconnect", () => {
  beforeEach(() => {
    resetSockets();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("reconnects with backoff after an unexpected close", () => {
    const client = new ProtocolClient({
      url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: true, backoffBaseMs: 100,
    });
    client.connect();
    lastSocket().open();
    const firstSocket = lastSocket();
    firstSocket.serverClose();
    expect(client.getPhase()).toBe("reconnecting");
    vi.advanceTimersByTime(100);
    expect(FakeWebSocket.instances.length).toBe(2);
  });

  it("does not reconnect after disconnect()", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: true });
    client.connect();
    lastSocket().open();
    client.disconnect();
    vi.advanceTimersByTime(10000);
    expect(FakeWebSocket.instances.length).toBe(1);
    expect(client.getPhase()).toBe("closed");
  });
});

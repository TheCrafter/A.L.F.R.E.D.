import { create, type StoreApi, type UseBoundStore } from "zustand";
import type { StatusResponse } from "@alfred/protocol";
import {
  ProtocolClient,
  type ConnectionPhase,
  type ServerInfo,
  type WireEntry,
} from "../protocol/client";
import { fetchStatus, httpBaseFromWs } from "../protocol/status";
import { openTurn, applyMessage, finalizeOpenTurns, type Turn } from "./turns";
import { applyMemoryMessage, type MemoryState } from "./memories";

const WIRE_LIMIT = 500;

export interface AppState {
  phase: ConnectionPhase;
  server?: ServerInfo;
  lastError?: string;
  url: string;
  turns: Turn[];
  status?: StatusResponse;
  statusError?: string;
  wire: WireEntry[];
  memories: MemoryState;
  memoryFilter: "all" | "provisional";
  setUrl: (url: string) => void;
  connect: () => void;
  disconnect: () => void;
  submit: (text: string, scopeOverride?: string) => void;
  kill: (reason?: string) => void;
  refreshStatus: () => Promise<void>;
  confirmMemory: (id: string) => void;
  retagMemory: (id: string, tags: string[]) => void;
  removeMemory: (id: string) => void;
  setMemoryFilter: (f: "all" | "provisional") => void;
}

interface StoreDeps {
  clientFactory?: (url: string) => ProtocolClient;
  statusFn?: typeof fetchStatus;
}

export function createStore(
  deps: StoreDeps = {},
): UseBoundStore<StoreApi<AppState>> {
  const clientFactory = deps.clientFactory ?? ((url) => new ProtocolClient({ url }));
  const statusFn = deps.statusFn ?? fetchStatus;
  let client: ProtocolClient | null = null;

  return create<AppState>((set, get) => ({
    phase: "idle",
    url: "ws://127.0.0.1:8767/ws",
    turns: [],
    wire: [],
    memories: {},
    memoryFilter: "all",

    setUrl: (url) => set({ url }),

    connect: () => {
      client?.disconnect();
      const c = clientFactory(get().url);
      client = c;
      c.on("phase", (e) => {
        // A drop (reconnecting/closed) orphans any in-flight turn — finalize it
        // so it doesn't hang open with no status.
        const dropped = e.phase === "reconnecting" || e.phase === "closed";
        set({
          phase: e.phase,
          server: e.server ?? get().server,
          lastError: e.error,
          ...(dropped
            ? { turns: finalizeOpenTurns(get().turns, new Date().toISOString()) }
            : {}),
        });
        if (e.phase === "ready") c.requestMemoryList();
      });
      c.on("message", (m) => set({
        turns: applyMessage(get().turns, m),
        memories: applyMemoryMessage(get().memories, m),
      }));
      c.on("wire", (w) => set({ wire: [...get().wire, w].slice(-WIRE_LIMIT) }));
      c.connect();
    },

    disconnect: () => client?.disconnect(),

    submit: (text, scopeOverride) => {
      if (!client) return;
      const corr = client.submitCommand(text, scopeOverride ? { scopeOverride } : {});
      set({
        turns: openTurn(get().turns, {
          corr,
          commandText: text,
          ...(scopeOverride ? { scopeOverride } : {}),
          at: new Date().toISOString(),
        }),
      });
    },

    kill: (reason) => client?.activateKillSwitch(reason),

    confirmMemory: (id) => client?.editMemory(id, { status: "confirmed" }),
    retagMemory: (id, tags) => client?.editMemory(id, { tags }),
    removeMemory: (id) => client?.deleteMemory(id),
    setMemoryFilter: (f) => set({ memoryFilter: f }),

    refreshStatus: async () => {
      try {
        const status = await statusFn(httpBaseFromWs(get().url));
        set({ status, statusError: undefined });
      } catch (err) {
        set({ statusError: err instanceof Error ? err.message : String(err) });
      }
    },
  }));
}

export const useStore = createStore();

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
  setUrl: (url: string) => void;
  connect: () => void;
  disconnect: () => void;
  submit: (text: string, scopeOverride?: string) => void;
  kill: (reason?: string) => void;
  refreshStatus: () => Promise<void>;
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
      });
      c.on("message", (m) => set({ turns: applyMessage(get().turns, m) }));
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

import { describe, it, expect, beforeEach } from "vitest";
import { createStore } from "./store";
import { ProtocolClient } from "../protocol/client";
import { FakeWebSocket, lastSocket, resetSockets } from "../test/fake-websocket";

const Ctor = FakeWebSocket as unknown as { new (url: string): WebSocket };

function makeStore() {
  return createStore({
    clientFactory: (url) =>
      new ProtocolClient({ url, WebSocketCtor: Ctor, reconnect: false }),
    statusFn: async () => ({
      v: 1, id: "s", ts: "2026-06-23T00:00:00Z", type: "status.response",
      corr: "http-status", uptime_seconds: 1, server_version: "0.1.0",
      active_scopes: ["coding"], busy: false,
    }),
  });
}

const serverHello = {
  v: 1, id: "s-1", ts: "2026-06-23T00:00:00Z", type: "server.hello",
  corr: "ui-1-0", server_name: "m", server_version: "0.1.0",
  protocol_version: 1, session_id: "sess",
};

describe("store", () => {
  beforeEach(() => resetSockets());

  it("connects and reaches ready", () => {
    const useStore = makeStore();
    useStore.getState().connect();
    lastSocket().open();
    lastSocket().receive(serverHello);
    expect(useStore.getState().phase).toBe("ready");
    expect(useStore.getState().server?.sessionId).toBe("sess");
  });

  it("opens a turn on submit and routes the brain's reply", () => {
    const useStore = makeStore();
    useStore.getState().connect();
    const ws = lastSocket();
    ws.open();
    ws.receive(serverHello);
    useStore.getState().submit("check the build");
    const corr = useStore.getState().turns[0].corr;
    ws.receive({ v: 1, id: "a", ts: "2026-06-23T00:00:00Z", type: "agent.message", corr, text: "done.", final: true });
    expect(useStore.getState().turns[0].message.text).toBe("done.");
  });

  it("records wire entries", () => {
    const useStore = makeStore();
    useStore.getState().connect();
    lastSocket().open();
    lastSocket().receive(serverHello);
    expect(useStore.getState().wire.length).toBeGreaterThan(0);
  });

  it("refreshStatus stores the response", async () => {
    const useStore = makeStore();
    await useStore.getState().refreshStatus();
    expect(useStore.getState().status?.active_scopes).toEqual(["coding"]);
  });
});

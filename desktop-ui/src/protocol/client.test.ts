import { describe, it, expect, beforeEach } from "vitest";
import { ProtocolClient } from "./client";
import type { PhaseEvent, WireEntry } from "./client";
import { FakeWebSocket, lastSocket, resetSockets } from "../test/fake-websocket";

function makeClient() {
  return new ProtocolClient({
    url: "ws://127.0.0.1:8765/ws",
    WebSocketCtor: FakeWebSocket as unknown as { new (url: string): WebSocket },
    reconnect: false,
  });
}

const serverHello = {
  v: 1,
  id: "s-1",
  ts: "2026-06-23T00:00:00Z",
  type: "server.hello",
  corr: "ui-1-0",
  server_name: "alfred-mock-brain",
  server_version: "0.1.0",
  protocol_version: 1,
  session_id: "mock-session",
};

describe("ProtocolClient handshake", () => {
  beforeEach(() => resetSockets());

  it("sends client.hello on open and goes ready on server.hello", () => {
    const phases: PhaseEvent[] = [];
    const client = makeClient();
    client.on("phase", (e) => phases.push(e));
    client.connect();

    const ws = lastSocket();
    expect(phases.at(-1)?.phase).toBe("connecting");
    ws.open();
    expect(phases.at(-1)?.phase).toBe("handshaking");

    const sent = JSON.parse(ws.sent[0]);
    expect(sent.type).toBe("client.hello");
    expect(sent.protocol_version).toBe(1);
    expect(sent.client_name).toBe("alfred-desktop-ui");

    ws.receive(serverHello);
    const ready = phases.at(-1);
    expect(ready?.phase).toBe("ready");
    expect(ready?.server?.sessionId).toBe("mock-session");
  });

  it("emits validated inbound messages and logs them to the wire", () => {
    const messages: string[] = [];
    const wire: WireEntry[] = [];
    const client = makeClient();
    client.on("message", (m) => messages.push(m.type));
    client.on("wire", (w) => wire.push(w));
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive(serverHello);

    expect(messages).toContain("server.hello");
    const inHello = wire.find((w) => w.direction === "in" && w.type === "server.hello");
    expect(inHello?.valid).toBe(true);
  });

  it("rejects a schema-invalid inbound message and enters error", () => {
    const phases: PhaseEvent[] = [];
    const messages: string[] = [];
    const client = makeClient();
    client.on("phase", (e) => phases.push(e));
    client.on("message", (m) => messages.push(m.type));
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive({ v: 1, id: "bad", ts: "nope", type: "server.hello" });

    expect(phases.at(-1)?.phase).toBe("error");
    expect(messages).not.toContain("server.hello");
  });

  it("enters error on an unsupported_version error", () => {
    const phases: PhaseEvent[] = [];
    const client = makeClient();
    client.on("phase", (e) => phases.push(e));
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive({
      v: 1,
      id: "e-1",
      ts: "2026-06-23T00:00:00Z",
      type: "error",
      code: "unsupported_version",
      message: "This server speaks protocol v2.",
    });
    expect(phases.at(-1)?.phase).toBe("error");
  });
});

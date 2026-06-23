// @vitest-environment node
// Opt-in: requires the mock brain running.
//   protocol/$ uv run uvicorn mock.server:app --port 8765
//   desktop-ui/$ ALFRED_MOCK_WS=ws://127.0.0.1:8765/ws pnpm exec vitest run src/protocol/integration.test.ts
import { describe, it, expect } from "vitest";
import { ProtocolClient } from "./client";
import type { Message } from "@alfred/protocol";

const WS_URL = process.env.ALFRED_MOCK_WS;

describe.skipIf(!WS_URL)("end-to-end against the mock brain", () => {
  it("completes a full command turn with only valid messages", async () => {
    const client = new ProtocolClient({ url: WS_URL!, reconnect: false });
    const seen: string[] = [];

    const done = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("timed out")), 5000);
      client.on("message", (m: Message) => {
        seen.push(m.type);
        if (m.type === "server.hello") client.submitCommand("check the build");
        if (m.type === "agent.turn_complete") {
          clearTimeout(timer);
          resolve();
        }
        if (m.type === "error") {
          clearTimeout(timer);
          reject(new Error(`server error: ${m.message}`));
        }
      });
      client.on("phase", (e) => {
        if (e.phase === "error") {
          clearTimeout(timer);
          reject(new Error(e.error ?? "connection error"));
        }
      });
      client.connect();
    });

    await done;
    client.disconnect();
    expect(seen).toContain("server.hello");
    expect(seen).toContain("agent.turn_complete");
  });
});

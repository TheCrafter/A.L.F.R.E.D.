import { describe, it, expect } from "vitest";
import { openTurn, applyMessage } from "./turns";
import type { Message } from "@alfred/protocol";

function start() {
  return openTurn([], { corr: "c1", commandText: "check the build", at: "2026-06-23T00:00:00Z" });
}

const msg = (m: Partial<Message> & { type: string }): Message =>
  ({ v: 1, id: "m", ts: "2026-06-23T00:00:00Z", ...m } as Message);

describe("turn reducer", () => {
  it("opens a turn", () => {
    const turns = start();
    expect(turns).toHaveLength(1);
    expect(turns[0].corr).toBe("c1");
    expect(turns[0].message.text).toBe("");
  });

  it("records ack, thought, and action by corr", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "command.ack", corr: "c1", accepted: true }));
    turns = applyMessage(turns, msg({ type: "agent.thought", corr: "c1", text: "thinking" }));
    turns = applyMessage(
      turns,
      msg({ type: "agent.action", corr: "c1", tool: "shell", summary: "run build", risk: "sensitive" }),
    );
    expect(turns[0].ack?.accepted).toBe(true);
    expect(turns[0].thoughts).toEqual(["thinking"]);
    expect(turns[0].actions[0]).toEqual({ tool: "shell", summary: "run build", risk: "sensitive" });
  });

  it("assembles streamed message chunks until final", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "agent.message", corr: "c1", text: "The build is ", final: false }));
    turns = applyMessage(turns, msg({ type: "agent.message", corr: "c1", text: "green, sir.", final: true }));
    expect(turns[0].message.text).toBe("The build is green, sir.");
    expect(turns[0].message.final).toBe(true);
  });

  it("records turn_complete status", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "agent.turn_complete", corr: "c1", status: "completed" }));
    expect(turns[0].status).toBe("completed");
  });

  it("ignores messages for unknown corr without throwing", () => {
    const turns = start();
    const next = applyMessage(turns, msg({ type: "agent.thought", corr: "nope", text: "x" }));
    expect(next[0].thoughts).toHaveLength(0);
  });

  it("ignores non-turn messages", () => {
    const turns = start();
    const next = applyMessage(turns, msg({ type: "status.request" }));
    expect(next).toEqual(turns);
  });
});

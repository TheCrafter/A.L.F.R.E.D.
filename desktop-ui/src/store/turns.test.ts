import { describe, it, expect } from "vitest";
import { openTurn, applyMessage, finalizeOpenTurns } from "./turns";
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
    expect(turns[0].endedAt).toBe("2026-06-23T00:00:00Z");
  });

  it("attaches a turn-scoped error to its turn", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "error", corr: "c1", code: "internal", message: "groq: 503" }));
    turns = applyMessage(turns, msg({ type: "agent.turn_complete", corr: "c1", status: "error" }));
    expect(turns[0].error).toEqual({ code: "internal", message: "groq: 503" });
    expect(turns[0].status).toBe("error");
  });

  it("ignores a connection-level error with no matching corr", () => {
    const turns = start();
    const next = applyMessage(turns, msg({ type: "error", code: "bad_message", message: "nope" }));
    expect(next[0].error).toBeUndefined();
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

  it("groups a multi-step turn: ordered thoughts, actions, then assembled message", () => {
    // A real multi-iteration turn: think -> act -> think -> act -> stream -> complete.
    let turns = start();
    const steps: Array<Partial<Message> & { type: string }> = [
      { type: "command.ack", corr: "c1", accepted: true },
      { type: "agent.thought", corr: "c1", text: "first, inspect" },
      { type: "agent.action", corr: "c1", tool: "echo", summary: "echo(a)", risk: "safe" },
      { type: "agent.thought", corr: "c1", text: "now, act" },
      { type: "agent.action", corr: "c1", tool: "shell", summary: "build", risk: "sensitive" },
      { type: "agent.message", corr: "c1", text: "All ", final: false },
      { type: "agent.message", corr: "c1", text: "done, sir.", final: true },
      { type: "agent.turn_complete", corr: "c1", status: "completed" },
    ];
    for (const s of steps) turns = applyMessage(turns, msg(s));
    const t = turns[0];
    expect(t.thoughts).toEqual(["first, inspect", "now, act"]);
    expect(t.actions.map((a) => a.tool)).toEqual(["echo", "shell"]);
    expect(t.actions[1].risk).toBe("sensitive");
    expect(t.message.text).toBe("All done, sir.");
    expect(t.message.final).toBe(true);
    expect(t.status).toBe("completed");
  });

  it("finalizes only open turns as interrupted on disconnect", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "agent.thought", corr: "c1", text: "mid-turn" }));
    turns = openTurn(turns, { corr: "c2", commandText: "done one", at: "2026-06-23T00:00:01Z" });
    turns = applyMessage(turns, msg({ type: "agent.turn_complete", corr: "c2", status: "completed" }));

    const next = finalizeOpenTurns(turns, "2026-06-23T00:00:05Z");
    expect(next[0].status).toBe("interrupted");
    expect(next[0].endedAt).toBe("2026-06-23T00:00:05Z");
    expect(next[1].status).toBe("completed"); // already terminal — untouched
  });
});

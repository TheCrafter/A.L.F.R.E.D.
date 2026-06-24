import { describe, expect, it } from "vitest";
import { applyMemoryMessage, type MemoryState } from "./memories";
import type { Message } from "@alfred/protocol";

const item = (id: string, status: "provisional" | "confirmed") => ({
  id, text: "t", title: "T", type: "fact", tags: [], status,
  created: "2026-06-24T20:11:00Z", links: [],
});

describe("applyMemoryMessage", () => {
  it("replaces on list_response", () => {
    const msg = { v: 1, id: "m1", ts: "x", type: "memory.list_response", corr: "c",
      items: [item("a", "confirmed")] } as unknown as Message;
    const next = applyMemoryMessage({}, msg);
    expect(Object.keys(next)).toEqual(["a"]);
  });
  it("upserts on formed", () => {
    const msg = { v: 1, id: "m2", ts: "x", type: "memory.formed", op: "add",
      item: item("b", "provisional") } as unknown as Message;
    const next = applyMemoryMessage({}, msg);
    expect(next.b.status).toBe("provisional");
  });
  it("deletes on removed", () => {
    const start: MemoryState = { a: item("a", "confirmed") };
    const msg = { v: 1, id: "m3", ts: "x", type: "memory.removed", mem_id: "a" } as unknown as Message;
    expect(applyMemoryMessage(start, msg)).toEqual({});
  });
  it("ignores unrelated messages", () => {
    const start: MemoryState = { a: item("a", "confirmed") };
    const msg = { type: "agent.message" } as unknown as Message;
    expect(applyMemoryMessage(start, msg)).toBe(start);
  });
});

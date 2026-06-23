import { describe, it, expect } from "vitest";
import { validateMessage } from "./validator";

describe("validateMessage", () => {
  it("accepts a well-formed message", () => {
    const r = validateMessage({
      v: 1,
      id: "x",
      ts: "2026-06-23T00:00:00Z",
      type: "command.submit",
      text: "hi",
      channel: "desktop",
    });
    expect(r.valid).toBe(true);
  });

  it("rejects a message with a bad timestamp", () => {
    const r = validateMessage({
      v: 1,
      id: "x",
      ts: "not-a-date",
      type: "command.submit",
      text: "hi",
      channel: "desktop",
    });
    expect(r.valid).toBe(false);
    expect(r.errors).toBeTruthy();
  });

  it("rejects a message with an unknown type", () => {
    const r = validateMessage({ v: 1, id: "x", ts: "2026-06-23T00:00:00Z", type: "nope" });
    expect(r.valid).toBe(false);
  });
});

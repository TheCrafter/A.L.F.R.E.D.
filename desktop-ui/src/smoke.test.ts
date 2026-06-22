import { describe, it, expect } from "vitest";
import type { Message } from "@alfred/protocol";
import schema from "@alfred/protocol-schema";

describe("contract wiring", () => {
  it("imports a protocol type and the schema", () => {
    const msg: Message = {
      v: 1,
      id: "t-1",
      ts: "2026-06-23T00:00:00Z",
      type: "status.request",
    };
    expect(msg.type).toBe("status.request");
    expect((schema as { title?: string }).title).toBe("Message");
  });
});

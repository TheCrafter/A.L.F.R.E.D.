import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WireInspector } from "./WireInspector";
import { useStore } from "../store/store";

describe("WireInspector", () => {
  beforeEach(() =>
    useStore.setState({
      wire: [
        { entryId: "w1", direction: "in", type: "server.hello", raw: { type: "server.hello" }, valid: true, at: "t" },
        { entryId: "w2", direction: "out", type: "command.submit", raw: { type: "command.submit" }, valid: true, at: "t" },
      ],
    }),
  );

  it("toggles open to reveal wire entries", async () => {
    render(<WireInspector />);
    expect(screen.queryByText(/server\.hello/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /wire/i }));
    expect(screen.getByText(/server\.hello/)).toBeInTheDocument();
    expect(screen.getByText(/command\.submit/)).toBeInTheDocument();
  });
});

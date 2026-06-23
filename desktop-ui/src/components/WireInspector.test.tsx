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
    expect(screen.getAllByText(/server\.hello/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/command\.submit/).length).toBeGreaterThan(0);
  });

  it("shows the failure badge for invalid entries", async () => {
    useStore.setState({
      wire: [{ entryId: "w3", direction: "in", type: "error", raw: { type: "error" }, valid: false, at: "t" }],
    });
    render(<WireInspector />);
    await userEvent.click(screen.getByRole("button", { name: /wire/i }));
    expect(screen.getByText("✗")).toBeInTheDocument();
  });
});

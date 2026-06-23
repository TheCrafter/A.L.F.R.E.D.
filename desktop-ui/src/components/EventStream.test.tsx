import { describe, it, expect, beforeEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EventStream } from "./EventStream";
import { useStore } from "../store/store";
import type { Turn } from "../store/turns";

function mkTurn(corr: string, commandText: string, reply: string): Turn {
  return {
    corr,
    commandText,
    channel: "desktop",
    thoughts: [],
    actions: [],
    message: { text: reply, final: true },
    status: "completed",
    startedAt: "2026-06-23T00:00:00Z",
  };
}

describe("EventStream", () => {
  beforeEach(() => useStore.setState({ turns: [] }));

  it("collapses and expands a turn from its header", async () => {
    useStore.setState({ turns: [mkTurn("c1", "write a poem", "Here is your poem, sir.")] });
    render(<EventStream />);
    const header = screen.getByRole("button", { name: /write a poem/ });
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Here is your poem/)).toBeInTheDocument();

    await userEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Here is your poem/)).toBeNull();

    await userEvent.click(header);
    expect(screen.getByText(/Here is your poem/)).toBeInTheDocument();
  });

  it("renders newest first and auto-collapses older turns", () => {
    useStore.setState({
      turns: [mkTurn("c1", "first cmd", "first reply"), mkTurn("c2", "second cmd", "second reply")],
    });
    render(<EventStream />);
    const headers = screen.getAllByRole("button");
    expect(headers[0]).toHaveAccessibleName(/second cmd/); // newest on top
    expect(headers[1]).toHaveAccessibleName(/first cmd/);
    expect(headers[0]).toHaveAttribute("aria-expanded", "true");
    expect(headers[1]).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("second reply")).toBeInTheDocument();
    expect(screen.queryByText("first reply")).toBeNull();
  });

  it("keeps a manually-expanded older turn open when a new turn arrives", async () => {
    useStore.setState({
      turns: [mkTurn("c1", "old cmd", "old reply"), mkTurn("c2", "new cmd", "new reply")],
    });
    render(<EventStream />);
    await userEvent.click(screen.getByRole("button", { name: /old cmd/ }));
    expect(screen.getByText("old reply")).toBeInTheDocument();

    // a newer turn arrives — the manually-opened older turn must stay open
    act(() => {
      useStore.setState({
        turns: [
          mkTurn("c1", "old cmd", "old reply"),
          mkTurn("c2", "new cmd", "new reply"),
          mkTurn("c3", "newest cmd", "newest reply"),
        ],
      });
    });
    expect(screen.getByText("old reply")).toBeInTheDocument();
    expect(screen.getByText("newest reply")).toBeInTheDocument();
  });
});

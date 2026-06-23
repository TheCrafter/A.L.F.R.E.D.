import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EventStream } from "./EventStream";
import { useStore } from "../store/store";
import type { Turn } from "../store/turns";

const turn: Turn = {
  corr: "c1",
  commandText: "write a poem",
  channel: "desktop",
  thoughts: [],
  actions: [],
  message: { text: "Here is your poem, sir.", final: true },
  status: "completed",
  startedAt: "2026-06-23T00:00:00Z",
};

describe("EventStream", () => {
  beforeEach(() => useStore.setState({ turns: [turn] }));

  it("collapses and expands a turn from its header", async () => {
    render(<EventStream />);
    expect(screen.getByText(/Here is your poem/)).toBeInTheDocument();
    const header = screen.getByRole("button", { name: /write a poem/ });
    expect(header).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Here is your poem/)).toBeNull();

    await userEvent.click(header);
    expect(screen.getByText(/Here is your poem/)).toBeInTheDocument();
  });
});

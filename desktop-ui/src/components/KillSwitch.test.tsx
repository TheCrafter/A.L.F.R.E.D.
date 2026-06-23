import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KillSwitch } from "./KillSwitch";
import { useStore } from "../store/store";

describe("KillSwitch", () => {
  beforeEach(() => useStore.setState({ phase: "ready" }));

  it("requires confirmation, then calls kill", async () => {
    const kill = vi.fn();
    useStore.setState({ kill });
    render(<KillSwitch />);
    await userEvent.click(screen.getByRole("button", { name: /kill switch/i }));
    expect(kill).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /^confirm halt$/i }));
    expect(kill).toHaveBeenCalledTimes(1);
  });
});

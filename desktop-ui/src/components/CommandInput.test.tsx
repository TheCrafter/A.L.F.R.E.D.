import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommandInput } from "./CommandInput";
import { useStore } from "../store/store";

describe("CommandInput", () => {
  beforeEach(() => useStore.setState({ phase: "ready", turns: [] }));

  it("submits the typed command via the store", async () => {
    const submit = vi.fn();
    useStore.setState({ submit });
    render(<CommandInput />);
    await userEvent.type(screen.getByPlaceholderText(/command/i), "check the build");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(submit).toHaveBeenCalledWith("check the build", undefined);
  });

  it("is disabled when not ready", () => {
    useStore.setState({ phase: "idle" });
    render(<CommandInput />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });
});

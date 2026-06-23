import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { AlfredCore } from "./AlfredCore";
import { useStore } from "../store/store";
import type { Turn } from "../store/turns";

function turn(over: Partial<Turn>): Turn {
  return {
    corr: "c1",
    commandText: "do it",
    channel: "desktop",
    thoughts: [],
    actions: [],
    message: { text: "", final: false },
    startedAt: "2026-06-23T00:00:00Z",
    ...over,
  };
}

describe("AlfredCore", () => {
  beforeEach(() => useStore.setState({ phase: "idle", turns: [], status: undefined }));

  it("reads OFFLINE when not connected", () => {
    useStore.setState({ phase: "idle" });
    render(<AlfredCore />);
    expect(screen.getByText("OFFLINE")).toBeInTheDocument();
  });

  it("reads ONLINE when ready and idle, with a persona line", () => {
    useStore.setState({ phase: "ready", turns: [] });
    render(<AlfredCore />);
    expect(screen.getByText("ONLINE")).toBeInTheDocument();
    expect(screen.getByText(/standing by/i)).toBeInTheDocument();
  });

  it("reads SPEAKING and shows the streamed text while a reply streams", () => {
    useStore.setState({
      phase: "ready",
      turns: [turn({ message: { text: "The build is", final: false } })],
    });
    render(<AlfredCore />);
    expect(screen.getByText("SPEAKING")).toBeInTheDocument();
    expect(screen.getByText(/the build is/i)).toBeInTheDocument();
  });

  it("reads PROCESSING when the agent is acting but not yet speaking", () => {
    useStore.setState({
      phase: "ready",
      turns: [turn({ thoughts: ["inspecting"], message: { text: "", final: false } })],
    });
    render(<AlfredCore />);
    expect(screen.getByText("PROCESSING")).toBeInTheDocument();
  });
});

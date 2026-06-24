import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { MemoryPanel } from "./MemoryPanel";
import { useStore } from "../store/store";
import type { MemoryItem } from "@alfred/protocol";

function mkMemory(id: string, status: "provisional" | "confirmed", title: string): MemoryItem {
  return {
    id,
    title,
    text: `Body of ${title}`,
    type: "fact",
    tags: [],
    status,
    created: `2026-06-23T0${id}:00:00Z`,
    links: [],
  };
}

describe("MemoryPanel", () => {
  beforeEach(() => {
    useStore.setState({
      memories: {},
      memoryFilter: "all",
      confirmMemory: vi.fn(),
      removeMemory: vi.fn(),
      retagMemory: vi.fn(),
    } as Partial<ReturnType<typeof useStore.getState>> as Parameters<typeof useStore.setState>[0]);
  });

  it("renders a card per memory with title and status badge", () => {
    useStore.setState({
      memories: {
        "1": mkMemory("1", "confirmed", "First memory"),
        "2": mkMemory("2", "provisional", "Second memory"),
      },
    });
    render(<MemoryPanel />);
    expect(screen.getByText("First memory")).toBeInTheDocument();
    expect(screen.getByText("Second memory")).toBeInTheDocument();
    // "confirmed" appears only as a badge (no filter button for it).
    // "provisional" appears as a filter button AND as a badge = 2 total.
    expect(screen.getAllByText("confirmed")).toHaveLength(1);
    expect(screen.getAllByText("provisional")).toHaveLength(2);
  });

  it("clicking Confirm on a provisional card calls confirmMemory with its id", () => {
    const confirmMemory = vi.fn();
    useStore.setState({
      memories: { "1": mkMemory("1", "provisional", "Provisional memory") },
      confirmMemory,
    });
    render(<MemoryPanel />);
    fireEvent.click(screen.getByText("Confirm"));
    expect(confirmMemory).toHaveBeenCalledWith("1");
  });

  it("clicking Delete calls removeMemory with the card id", () => {
    const removeMemory = vi.fn();
    useStore.setState({
      memories: { "1": mkMemory("1", "confirmed", "Confirmed memory") },
      removeMemory,
    });
    render(<MemoryPanel />);
    fireEvent.click(screen.getByText("Delete"));
    expect(removeMemory).toHaveBeenCalledWith("1");
  });

  it("the provisional filter hides confirmed cards", () => {
    useStore.setState({
      memories: {
        "1": mkMemory("1", "confirmed", "Confirmed memory"),
        "2": mkMemory("2", "provisional", "Provisional memory"),
      },
      memoryFilter: "provisional",
    });
    render(<MemoryPanel />);
    expect(screen.queryByText("Confirmed memory")).toBeNull();
    expect(screen.getByText("Provisional memory")).toBeInTheDocument();
  });

  it("renders existing tags as chips", () => {
    useStore.setState({
      memories: { "1": { ...mkMemory("1", "confirmed", "Mem"), tags: ["alpha", "beta"] } },
      retagMemory: vi.fn(),
    });
    render(<MemoryPanel />);
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
  });

  it("typing a tag and pressing Enter calls retagMemory with the new tag appended", () => {
    const retagMemory = vi.fn();
    useStore.setState({
      memories: { "1": { ...mkMemory("1", "confirmed", "Mem"), tags: ["existing"] } },
      retagMemory,
    });
    render(<MemoryPanel />);
    const input = screen.getByPlaceholderText("add tag…");
    fireEvent.change(input, { target: { value: "new" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(retagMemory).toHaveBeenCalledWith("1", ["existing", "new"]);
  });

  it("clicking × on a tag chip calls retagMemory without that tag", () => {
    const retagMemory = vi.fn();
    useStore.setState({
      memories: { "1": { ...mkMemory("1", "confirmed", "Mem"), tags: ["only"] } },
      retagMemory,
    });
    render(<MemoryPanel />);
    fireEvent.click(screen.getByRole("button", { name: "remove tag only" }));
    expect(retagMemory).toHaveBeenCalledWith("1", []);
  });
});

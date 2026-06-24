import { useState } from "react";
import { useStore } from "../store/store";
import type { MemoryItem } from "@alfred/protocol";

const STATUS_STYLE: Record<string, string> = {
  confirmed: "text-safe border-safe/40",
  provisional: "text-amber border-amber/40",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${STATUS_STYLE[status] ?? "text-hud-dim border-hud-dim/40"}`}>
      {status}
    </span>
  );
}

function TagInput({
  itemId, currentTags, retagMemory,
}: {
  itemId: string;
  currentTags: string[];
  retagMemory: (id: string, tags: string[]) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <input
      className="mt-1 w-full rounded border border-hud-dim/30 bg-transparent px-1 py-0.5 text-[10px] text-hud-dim placeholder:text-hud-dim/50"
      placeholder="add tag…"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => {
        if (e.key !== "Enter") return;
        const tag = value.trim();
        if (!tag || currentTags.includes(tag)) return;
        retagMemory(itemId, [...currentTags, tag]);
        setValue("");
      }}
    />
  );
}

function MemoryCard({ item }: { item: MemoryItem }) {
  const confirmMemory = useStore((s) => s.confirmMemory);
  const removeMemory = useStore((s) => s.removeMemory);
  const retagMemory = useStore((s) => s.retagMemory);
  return (
    <div className="rounded border border-hud-dim/30 bg-panel/60 p-2">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm text-hud">{item.title}</span>
        <StatusBadge status={item.status} />
      </div>
      <p className="mt-1 text-xs text-hud-dim">{item.text}</p>
      {item.links.length > 0 && (
        <p className="mt-1 text-[10px] uppercase tracking-wider text-hud-dim">
          {item.links.join(" · ")}
        </p>
      )}
      {item.tags.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {item.tags.map((tag) => (
            <span key={tag} className="flex items-center gap-0.5 rounded border border-hud-dim/30 px-1 py-0.5 text-[10px] text-hud-dim">
              {tag}
              <button
                aria-label={`remove tag ${tag}`}
                className="text-[10px] leading-none text-hud-dim hover:text-danger"
                onClick={() => retagMemory(item.id, item.tags.filter((t) => t !== tag))}
              >×</button>
            </span>
          ))}
        </div>
      )}
      <TagInput itemId={item.id} currentTags={item.tags} retagMemory={retagMemory} />
      <div className="mt-2 flex gap-2">
        {item.status === "provisional" && (
          <button className="text-[10px] uppercase tracking-wider text-safe"
                  onClick={() => confirmMemory(item.id)}>Confirm</button>
        )}
        <button className="text-[10px] uppercase tracking-wider text-danger"
                onClick={() => removeMemory(item.id)}>Delete</button>
      </div>
    </div>
  );
}

export function MemoryPanel() {
  const memories = useStore((s) => s.memories);
  const filter = useStore((s) => s.memoryFilter);
  const setFilter = useStore((s) => s.setMemoryFilter);
  const items = Object.values(memories)
    .filter((m) => filter === "all" || m.status === "provisional")
    .sort((a, b) => b.created.localeCompare(a.created));

  return (
    <section className="flex min-h-0 flex-col gap-2 border-l border-hud-dim/30 bg-panel/40 p-3">
      <header className="flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-widest text-hud-dim">Memory</h2>
        <div className="flex gap-1">
          {(["all", "provisional"] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`text-[10px] uppercase tracking-wider ${filter === f ? "text-hud" : "text-hud-dim"}`}>
              {f}
            </button>
          ))}
        </div>
      </header>
      <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
        {items.length === 0
          ? <p className="text-xs text-hud-dim">No memories yet.</p>
          : items.map((m) => <MemoryCard key={m.id} item={m} />)}
      </div>
    </section>
  );
}

import { useState } from "react";
import { useStore } from "../store/store";

function rawPreview(raw: unknown): string {
  if (raw !== null && typeof raw === "object" && !Array.isArray(raw)) {
    const { type: _type, ...rest } = raw as Record<string, unknown>;
    void _type;
    return JSON.stringify(rest);
  }
  return JSON.stringify(raw);
}

export function WireInspector() {
  const wire = useStore((s) => s.wire);
  const [open, setOpen] = useState(false);

  return (
    <section className="border-t border-hud-dim/30 bg-void/80">
      <button
        className="flex w-full items-center gap-2 px-4 py-1 text-[10px] uppercase tracking-[0.3em] text-hud-dim"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "▼" : "▶"} Wire · {wire.length}
      </button>
      {open && (
        <div className="max-h-48 overflow-y-auto px-4 pb-2 font-mono text-[11px]">
          {wire.map((e) => (
            <div key={e.entryId} className="flex gap-2 border-b border-hud-dim/10 py-0.5">
              <span className={e.direction === "in" ? "text-hud" : "text-amber"}>
                {e.direction === "in" ? "◀" : "▶"}
              </span>
              <span className={e.valid ? "text-safe" : "text-danger"}>
                {e.valid ? "✓" : "✗"}
              </span>
              <span className="text-hud-dim">{e.type}</span>
              <span className="truncate text-hud-dim/60">{rawPreview(e.raw)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

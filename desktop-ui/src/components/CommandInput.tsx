import { useState } from "react";
import { useStore } from "../store/store";

export function CommandInput() {
  const phase = useStore((s) => s.phase);
  const submit = useStore((s) => s.submit);
  const [text, setText] = useState("");
  const [scope, setScope] = useState("");
  const ready = phase === "ready";

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed || !ready) return;
    submit(trimmed, scope.trim() || undefined);
    setText("");
    setScope("");
  };

  return (
    <div className="flex gap-2 border-t border-hud-dim/30 bg-panel/60 p-3">
      <input
        className="w-32 rounded bg-void px-2 py-1 text-xs text-hud outline-none placeholder:text-hud-dim"
        placeholder="scope (optional)"
        value={scope}
        onChange={(e) => setScope(e.target.value)}
      />
      <input
        className="flex-1 rounded bg-void px-3 py-1 text-sm text-hud outline-none placeholder:text-hud-dim"
        placeholder="Issue a command, sir…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && send()}
      />
      <button
        className="rounded border border-hud px-4 py-1 text-sm uppercase tracking-wide text-hud disabled:opacity-30"
        onClick={send}
        disabled={!ready}
      >
        Send
      </button>
    </div>
  );
}

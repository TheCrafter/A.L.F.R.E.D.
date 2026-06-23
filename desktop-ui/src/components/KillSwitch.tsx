import { useState } from "react";
import { useStore } from "../store/store";

export function KillSwitch() {
  const kill = useStore((s) => s.kill);
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-danger">Halt all agent action now?</span>
        <button
          className="rounded bg-danger px-3 py-1 text-xs font-bold uppercase text-void"
          onClick={() => {
            kill("operator pressed kill switch");
            setConfirming(false);
          }}
        >
          Confirm halt
        </button>
        <button
          className="rounded border border-hud-dim px-3 py-1 text-xs uppercase text-hud-dim"
          onClick={() => setConfirming(false)}
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      className="rounded border-2 border-danger px-4 py-1 text-xs font-bold uppercase tracking-wider text-danger hover:bg-danger hover:text-void"
      onClick={() => setConfirming(true)}
    >
      Kill switch
    </button>
  );
}

import { useEffect } from "react";
import { useStore } from "../store/store";

export function StatusPanel() {
  const status = useStore((s) => s.status);
  const statusError = useStore((s) => s.statusError);
  const refreshStatus = useStore((s) => s.refreshStatus);
  const phase = useStore((s) => s.phase);

  useEffect(() => {
    if (phase !== "ready") return;
    void refreshStatus();
    const t = setInterval(() => void refreshStatus(), 5000);
    return () => clearInterval(t);
  }, [phase, refreshStatus]);

  return (
    <aside className="w-64 space-y-2 border-l border-hud-dim/30 bg-panel/50 p-4 text-xs">
      <h2 className="text-[10px] uppercase tracking-[0.3em] text-hud-dim">Status</h2>
      {statusError && <p className="break-all text-danger">{statusError}</p>}
      {status ? (
        <dl className="space-y-1 text-hud-dim">
          <Row k="uptime" v={`${status.uptime_seconds.toFixed(0)}s`} />
          <Row k="version" v={status.server_version} />
          <Row k="scopes" v={status.active_scopes.join(", ") || "—"} />
          <Row k="busy" v={status.busy ? "yes" : "no"} />
        </dl>
      ) : (
        <p className="text-hud-dim">No reading yet.</p>
      )}
    </aside>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <dt>{k}</dt>
      <dd className="text-hud">{v}</dd>
    </div>
  );
}

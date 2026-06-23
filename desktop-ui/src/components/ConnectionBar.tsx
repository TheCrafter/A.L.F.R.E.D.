import { useStore } from "../store/store";

const DOT: Record<string, string> = {
  ready: "bg-safe",
  connecting: "bg-amber",
  handshaking: "bg-amber",
  reconnecting: "bg-amber",
  idle: "bg-hud-dim",
  closed: "bg-hud-dim",
  error: "bg-danger",
};

export function ConnectionBar() {
  const { phase, url, server, setUrl, connect, disconnect, lastError } = useStore();
  const connected = phase === "ready";

  return (
    <header className="flex items-center gap-3 border-b border-hud-dim/30 bg-panel/80 px-4 py-2">
      <span
        className={`h-3 w-3 rounded-full ${DOT[phase] ?? "bg-hud-dim"} ${["connecting", "handshaking", "ready", "reconnecting"].includes(phase) ? "animate-pulse" : ""}`}
      />
      <span className="text-lg font-bold tracking-[0.3em] text-hud">ALFRED</span>
      <input
        className="w-72 rounded bg-void px-2 py-1 text-xs text-hud-dim outline-none"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={connected}
      />
      <button
        className="rounded border border-hud px-3 py-1 text-xs uppercase text-hud"
        onClick={connected ? disconnect : connect}
      >
        {connected ? "Disconnect" : "Connect"}
      </button>
      <span className="ml-auto text-xs text-hud-dim">
        {server ? `${server.serverName} v${server.serverVersion} · ${server.sessionId}` : phase}
        {lastError ? ` · ${lastError}` : ""}
      </span>
    </header>
  );
}

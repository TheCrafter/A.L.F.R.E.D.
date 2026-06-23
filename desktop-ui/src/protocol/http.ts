export function isTauri(): boolean {
  return (
    typeof window !== "undefined" &&
    ("__TAURI_INTERNALS__" in window || "__TAURI__" in window)
  );
}

export interface HttpResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

export type HttpGet = (url: string) => Promise<HttpResponse>;

// In Tauri, route through the HTTP plugin to bypass webview CORS; in a plain
// browser, use the global fetch (same-origin path goes through the Vite proxy).
export async function defaultGet(url: string): Promise<HttpResponse> {
  if (isTauri()) {
    // Non-literal specifier + @vite-ignore so Vite leaves this as a runtime-only
    // dynamic import (never statically resolved at build time). The package is
    // installed in Task 12; this branch is unreachable until isTauri() is true.
    const pkg = "@tauri-apps/plugin-http";
    const { fetch: tauriFetch } = (await import(
      /* @vite-ignore */ pkg
    )) as typeof import("@tauri-apps/plugin-http");
    const res = await tauriFetch(url, { method: "GET" });
    return { ok: res.ok, status: res.status, json: () => res.json() };
  }
  const res = await fetch(url, { method: "GET" });
  return { ok: res.ok, status: res.status, json: () => res.json() };
}

export function statusUrlFor(baseUrl: string): string {
  return isTauri() ? `${baseUrl}/status` : "/status";
}

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
    // Lazily import the Tauri HTTP plugin so it is only loaded inside the
    // webview (never in browser dev or tests). The package is a real dependency
    // (installed in Task 12), so Vite resolves and bundles this async chunk;
    // at runtime in Tauri the dynamic import resolves to that bundled chunk.
    const { fetch: tauriFetch } = await import("@tauri-apps/plugin-http");
    const res = await tauriFetch(url, { method: "GET" });
    return { ok: res.ok, status: res.status, json: () => res.json() };
  }
  const res = await fetch(url, { method: "GET" });
  return { ok: res.ok, status: res.status, json: () => res.json() };
}

export function statusUrlFor(baseUrl: string): string {
  return isTauri() ? `${baseUrl}/status` : "/status";
}

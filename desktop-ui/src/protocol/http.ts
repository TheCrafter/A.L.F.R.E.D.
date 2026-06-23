import { fetch as tauriFetch } from "@tauri-apps/plugin-http";

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
export type HttpPost = (url: string, body: unknown) => Promise<HttpResponse>;

// In Tauri, route through the HTTP plugin to bypass webview CORS; in a plain
// browser, use the global fetch (same-origin path goes through the Vite proxy).
// The plugin is imported statically (not via a runtime-gated dynamic import):
// merely importing it has no side effects, and a static import lets Vite bundle
// it with the main graph — avoiding the dev-server re-optimization race that a
// conditional dynamic import triggers ("Failed to fetch dynamically imported
// module"). It is only *called* inside the webview, where isTauri() is true.
export async function defaultGet(url: string): Promise<HttpResponse> {
  if (isTauri()) {
    const res = await tauriFetch(url, { method: "GET" });
    return { ok: res.ok, status: res.status, json: () => res.json() };
  }
  const res = await fetch(url, { method: "GET" });
  return { ok: res.ok, status: res.status, json: () => res.json() };
}

export async function defaultPost(url: string, body: unknown): Promise<HttpResponse> {
  const init: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = isTauri() ? await tauriFetch(url, init) : await fetch(url, init);
  return { ok: res.ok, status: res.status, json: () => res.json() };
}

export function statusUrlFor(baseUrl: string): string {
  return isTauri() ? `${baseUrl}/status` : "/status";
}

export function modelsUrlFor(baseUrl: string): string {
  return isTauri() ? `${baseUrl}/models` : "/models";
}

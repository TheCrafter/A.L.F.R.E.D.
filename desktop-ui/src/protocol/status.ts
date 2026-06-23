import type { StatusResponse } from "@alfred/protocol";
import { validateMessage } from "./validator";
import { defaultGet, statusUrlFor, type HttpGet } from "./http";

export { statusUrlFor };

// Derive the HTTP origin for /status from the WebSocket url, so a single
// connection field points both transports at the same brain:
//   ws://127.0.0.1:8766/ws  ->  http://127.0.0.1:8766
//   wss://host/ws           ->  https://host
export function httpBaseFromWs(wsUrl: string): string {
  try {
    const u = new URL(wsUrl);
    const proto = u.protocol === "wss:" ? "https:" : "http:";
    return `${proto}//${u.host}`;
  } catch {
    return wsUrl;
  }
}

export async function fetchStatus(
  baseUrl: string,
  deps: { get?: HttpGet; tauri?: boolean } = {},
): Promise<StatusResponse> {
  const get = deps.get ?? defaultGet;
  const url = deps.tauri ? `${baseUrl}/status` : statusUrlFor(baseUrl);
  const res = await get(url);
  if (!res.ok) throw new Error(`status request failed: HTTP ${res.status}`);
  const body = await res.json();
  const result = validateMessage(body);
  if (!result.valid) throw new Error(`invalid status.response: ${result.errors}`);
  return body as StatusResponse;
}

import type { StatusResponse } from "@alfred/protocol";
import { validateMessage } from "./validator";
import { defaultGet, statusUrlFor, type HttpGet } from "./http";

export { statusUrlFor };

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

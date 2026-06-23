// Stub for @tauri-apps/plugin-http — used only in browser/test environments
// where isTauri() is false so this code is never reached at runtime.
// The real plugin is added in Task 12 when Tauri v2 is wired up.
export async function fetch(
  _url: string,
  _options?: { method?: string },
): Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }> {
  throw new Error("@tauri-apps/plugin-http stub: should not be called outside Tauri");
}

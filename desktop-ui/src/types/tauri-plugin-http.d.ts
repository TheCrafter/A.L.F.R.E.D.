// Ambient type declaration for @tauri-apps/plugin-http.
// The real package is installed in Task 12; until then, this declaration
// satisfies tsc. The dynamic import in http.ts is only reached inside Tauri
// (isTauri() guard), so the stub module alias handles Vite/test resolution.
declare module "@tauri-apps/plugin-http" {
  export function fetch(
    url: string,
    options?: { method?: string },
  ): Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;
}

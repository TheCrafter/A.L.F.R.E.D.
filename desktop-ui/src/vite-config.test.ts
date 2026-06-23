// @vitest-environment node
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

// Regression: @tauri-apps/plugin-http is reached only through a runtime-gated
// dynamic import (see protocol/http.ts), so Vite does not pre-bundle it at cold
// start. The first /status fetch inside the Tauri webview then triggers an
// on-demand dep re-optimization that invalidates the module hash mid-flight,
// rejecting the in-flight import with "Failed to fetch dynamically imported
// module". Forcing it into optimizeDeps.include pre-bundles it deterministically.
const config = readFileSync(
  fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
  "utf8",
);

describe("vite dev bundling", () => {
  it("pre-bundles the Tauri http plugin via optimizeDeps.include", () => {
    expect(config).toMatch(/optimizeDeps\s*:/);
    const include = config.match(/include\s*:\s*\[([^\]]*)\]/);
    expect(include?.[1]).toContain("@tauri-apps/plugin-http");
  });
});

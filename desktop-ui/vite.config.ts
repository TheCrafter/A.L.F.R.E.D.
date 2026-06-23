/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const protocolTypes = fileURLToPath(
  new URL("../protocol/gen/typescript/index.ts", import.meta.url),
);
const protocolSchema = fileURLToPath(
  new URL("../protocol/schema/protocol.schema.json", import.meta.url),
);
const tauriHttpStub = fileURLToPath(
  new URL("./src/protocol/__stubs__/tauri-plugin-http.ts", import.meta.url),
);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@alfred/protocol": protocolTypes,
      "@alfred/protocol-schema": protocolSchema,
      // Stub for the Tauri HTTP plugin — not installed until Task 12.
      // isTauri() returns false in browser/test so this path is never reached.
      "@tauri-apps/plugin-http": tauriHttpStub,
    },
  },
  server: {
    port: 1420,
    strictPort: true,
    proxy: {
      "/status": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});

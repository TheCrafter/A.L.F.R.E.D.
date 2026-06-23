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

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@alfred/protocol": protocolTypes,
      "@alfred/protocol-schema": protocolSchema,
    },
  },
  server: {
    port: 1420,
    strictPort: true,
    proxy: {
      "/status": { target: "http://127.0.0.1:8767", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});

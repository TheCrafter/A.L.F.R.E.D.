import { describe, it, expect } from "vitest";
import { fetchStatus, statusUrlFor } from "./status";

const okStatus = {
  v: 1, id: "s", ts: "2026-06-23T00:00:00Z", type: "status.response",
  corr: "http-status", uptime_seconds: 12.5, server_version: "0.1.0",
  active_scopes: ["coding"], busy: false,
};

function fakeGet(body: unknown, ok = true) {
  return async () => ({ ok, status: ok ? 200 : 500, json: async () => body });
}

describe("fetchStatus", () => {
  it("returns a validated StatusResponse", async () => {
    const res = await fetchStatus("http://127.0.0.1:8765", { get: fakeGet(okStatus), tauri: true });
    expect(res.busy).toBe(false);
    expect(res.active_scopes).toEqual(["coding"]);
  });

  it("throws on a schema-invalid body", async () => {
    const bad = { ...okStatus, ts: "not-a-date" };
    await expect(
      fetchStatus("http://127.0.0.1:8765", { get: fakeGet(bad), tauri: true }),
    ).rejects.toThrow();
  });

  it("throws on a non-ok response", async () => {
    await expect(
      fetchStatus("http://127.0.0.1:8765", { get: fakeGet({}, false), tauri: true }),
    ).rejects.toThrow();
  });
});

describe("statusUrlFor", () => {
  it("uses the full URL under Tauri", () => {
    expect(statusUrlFor("http://127.0.0.1:8765")).toMatch(/\/status$/);
  });
});

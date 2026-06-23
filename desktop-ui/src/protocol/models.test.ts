import { describe, it, expect } from "vitest";
import { fetchModels, selectModel } from "./models";

const body = {
  current: { provider: "groq", model: "llama-3.3-70b-versatile" },
  available: [
    { provider: "scripted", model: "scripted" },
    { provider: "groq", model: "llama-3.3-70b-versatile" },
  ],
};

function fakeGet(payload: unknown, ok = true) {
  return async () => ({ ok, status: ok ? 200 : 500, json: async () => payload });
}

describe("fetchModels", () => {
  it("returns the parsed catalog", async () => {
    const res = await fetchModels("http://127.0.0.1:8767", { get: fakeGet(body) });
    expect(res.current.provider).toBe("groq");
    expect(res.available).toHaveLength(2);
  });

  it("throws on a non-ok response", async () => {
    await expect(fetchModels("http://x", { get: fakeGet({}, false) })).rejects.toThrow();
  });
});

describe("selectModel", () => {
  it("posts the selection and returns the new catalog", async () => {
    let sentUrl = "";
    let sentBody: unknown;
    const post = async (url: string, b: unknown) => {
      sentUrl = url;
      sentBody = b;
      return { ok: true, status: 200, json: async () => body };
    };
    const res = await selectModel("http://127.0.0.1:8767", { provider: "groq", model: "llama-3.3-70b-versatile" }, { post });
    expect(sentUrl).toMatch(/\/models$/);
    expect(sentBody).toEqual({ provider: "groq", model: "llama-3.3-70b-versatile" });
    expect(res.current.model).toBe("llama-3.3-70b-versatile");
  });

  it("surfaces the brain's error detail on failure", async () => {
    const post = async () => ({ ok: false, status: 400, json: async () => ({ detail: "GROQ_API_KEY is not set" }) });
    await expect(
      selectModel("http://x", { provider: "groq", model: "m" }, { post }),
    ).rejects.toThrow(/GROQ_API_KEY is not set/);
  });
});

import { defaultGet, defaultPost, modelsUrlFor, type HttpGet, type HttpPost } from "./http";

// /models is a brain admin endpoint (not part of the frozen WS contract): it
// lists the providers/models the running brain can switch to and which is live.
export interface ModelOption {
  provider: string;
  model: string;
}
export interface ModelsResponse {
  current: ModelOption;
  available: ModelOption[];
}

export async function fetchModels(
  baseUrl: string,
  deps: { get?: HttpGet } = {},
): Promise<ModelsResponse> {
  const get = deps.get ?? defaultGet;
  const res = await get(modelsUrlFor(baseUrl));
  if (!res.ok) throw new Error(`models request failed: HTTP ${res.status}`);
  return (await res.json()) as ModelsResponse;
}

export async function selectModel(
  baseUrl: string,
  opt: ModelOption,
  deps: { post?: HttpPost } = {},
): Promise<ModelsResponse> {
  const post = deps.post ?? defaultPost;
  const res = await post(modelsUrlFor(baseUrl), opt);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* non-JSON error body — keep the status-code message */
    }
    throw new Error(`model switch failed: ${detail}`);
  }
  return (await res.json()) as ModelsResponse;
}

import { useEffect, useState, type ChangeEvent } from "react";
import { useStore } from "../store/store";
import { httpBaseFromWs } from "../protocol/status";
import { fetchModels, selectModel, type ModelOption, type ModelsResponse } from "../protocol/models";

const keyOf = (o: ModelOption) => `${o.provider}:${o.model}`;

export function ModelPicker() {
  const phase = useStore((s) => s.phase);
  const url = useStore((s) => s.url);
  const [data, setData] = useState<ModelsResponse | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (phase !== "ready") return;
    let cancelled = false;
    fetchModels(httpBaseFromWs(url))
      .then((d) => !cancelled && (setData(d), setError(undefined)))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [phase, url]);

  if (phase !== "ready") return null;

  const onChange = async (e: ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    const idx = value.indexOf(":");
    const provider = value.slice(0, idx);
    const model = value.slice(idx + 1);
    setBusy(true);
    try {
      setData(await selectModel(httpBaseFromWs(url), { provider, model }));
      setError(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  // Always include the live model in the list, even if it is outside the catalog.
  const options = data
    ? data.available.some((o) => keyOf(o) === keyOf(data.current))
      ? data.available
      : [data.current, ...data.available]
    : [];

  return (
    <div className="space-y-1">
      <label className="text-[10px] uppercase tracking-[0.3em] text-hud-dim">Model</label>
      <select
        aria-label="Model"
        className="w-full rounded bg-void px-2 py-1 text-xs text-hud outline-none disabled:opacity-50"
        value={data ? keyOf(data.current) : ""}
        onChange={onChange}
        disabled={busy || !data}
      >
        {options.map((o) => (
          <option key={keyOf(o)} value={keyOf(o)}>
            {o.provider} · {o.model}
          </option>
        ))}
      </select>
      {error && <p className="break-all text-danger">{error}</p>}
    </div>
  );
}

import type { TurnAction } from "../store/turns";

const STYLES: Record<TurnAction["risk"], string> = {
  safe: "text-safe border-safe/40",
  sensitive: "text-amber border-amber/40",
  forbidden: "text-danger border-danger/40",
};

export function RiskBadge({ risk }: { risk: TurnAction["risk"] }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${STYLES[risk]}`}>
      {risk}
    </span>
  );
}

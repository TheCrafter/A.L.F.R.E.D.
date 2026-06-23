import type { Message } from "@alfred/protocol";

export interface TurnAction {
  tool: string;
  summary: string;
  risk: "safe" | "sensitive" | "forbidden";
}

export interface Turn {
  corr: string;
  commandText: string;
  channel: "desktop";
  scopeOverride?: string;
  ack?: { accepted: boolean; reason?: string };
  thoughts: string[];
  actions: TurnAction[];
  message: { text: string; final: boolean };
  // "interrupted" is a UI-local terminal status for turns orphaned by a
  // disconnect; the wire only carries completed | error | killed.
  status?: "completed" | "error" | "killed" | "interrupted";
  startedAt: string;
  endedAt?: string;
}

export function openTurn(
  turns: Turn[],
  params: { corr: string; commandText: string; scopeOverride?: string; at: string },
): Turn[] {
  const turn: Turn = {
    corr: params.corr,
    commandText: params.commandText,
    channel: "desktop",
    ...(params.scopeOverride ? { scopeOverride: params.scopeOverride } : {}),
    thoughts: [],
    actions: [],
    message: { text: "", final: false },
    startedAt: params.at,
  };
  return [...turns, turn];
}

// Mark every still-open turn (no terminal status) as interrupted. Called when
// the connection drops so orphaned turns don't hang open with no status.
export function finalizeOpenTurns(turns: Turn[], at: string): Turn[] {
  return turns.map((t) =>
    t.status ? t : { ...t, status: "interrupted", endedAt: at },
  );
}

export function applyMessage(turns: Turn[], msg: Message): Turn[] {
  if (
    msg.type !== "command.ack" &&
    msg.type !== "agent.thought" &&
    msg.type !== "agent.action" &&
    msg.type !== "agent.message" &&
    msg.type !== "agent.turn_complete"
  ) {
    return turns;
  }
  const corr = msg.corr;
  return turns.map((t) => {
    if (t.corr !== corr) return t;
    switch (msg.type) {
      case "command.ack":
        return {
          ...t,
          ack: { accepted: msg.accepted, ...(msg.reason ? { reason: msg.reason } : {}) },
        };
      case "agent.thought":
        return { ...t, thoughts: [...t.thoughts, msg.text] };
      case "agent.action":
        return {
          ...t,
          actions: [...t.actions, { tool: msg.tool, summary: msg.summary, risk: msg.risk }],
        };
      case "agent.message":
        return {
          ...t,
          message: { text: t.message.text + msg.text, final: msg.final },
        };
      case "agent.turn_complete":
        return { ...t, status: msg.status, endedAt: msg.ts };
      default:
        return t;
    }
  });
}

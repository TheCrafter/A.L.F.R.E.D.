import type { Message, MemoryItem } from "@alfred/protocol";

export type MemoryState = Record<string, MemoryItem>;

export function applyMemoryMessage(state: MemoryState, msg: Message): MemoryState {
  switch (msg.type) {
    case "memory.list_response": {
      const next: MemoryState = {};
      for (const it of msg.items) next[it.id] = it;
      return next;
    }
    case "memory.formed":
      return { ...state, [msg.item.id]: msg.item };
    case "memory.removed": {
      if (!(msg.mem_id in state)) return state;
      const next = { ...state };
      delete next[msg.mem_id];
      return next;
    }
    default:
      return state;
  }
}

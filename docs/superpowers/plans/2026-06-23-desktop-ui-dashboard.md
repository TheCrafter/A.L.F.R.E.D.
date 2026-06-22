# ALFRED Desktop UI Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `desktop-ui/` — a Tauri + React "JARVIS dashboard" that is a contract-valid client of the ALFRED brain (mock now, real later), rendering the live event stream and exposing command input, status, a kill switch, and a wire inspector.

**Architecture:** Three layers. (1) A framework-agnostic `ProtocolClient` owns the WebSocket, does the `client.hello`/`server.hello` handshake, Ajv-validates every inbound message, and exposes typed events. (2) A Zustand store turns those events into UI state (connection phase, turns keyed by `corr`, status, wire log). (3) React components render each surface. A Tauri v2 shell wraps the renderer last; `GET /status` routes through the Tauri HTTP plugin to dodge webview CORS.

**Tech Stack:** Vite 6 + React 18 + TypeScript (strict), Tailwind CSS v4, Zustand 5, Ajv 8 + ajv-formats, Vitest 2 + Testing Library + jsdom, Tauri v2 (Rust).

## Global Constraints

- **Contract-first.** Import generated **types** only: `import type { Message, … } from "@alfred/protocol"`. Never redefine a message shape. **Never edit anything under `protocol/`** — it is frozen. If a needed message genuinely does not exist, STOP and flag a coordinated protocol change.
- **Validate every inbound message** against `protocol/schema/protocol.schema.json` with `Ajv2020` + `ajv-formats`, exactly as `protocol/mock/client.ts` does.
- **Wire invariants:** optional fields are OMITTED when absent, never `null`. Every message carries the envelope `{ v: 1, id, ts (RFC 3339), type }`.
- **TypeScript strict mode**; never `any` — resolve types at the source.
- **No root pnpm workspace.** `desktop-ui/` is self-contained; resolve the contract via tsconfig path + Vite/Vitest aliases into `../protocol/`.
- **Commits:** plain, conventional, scoped `feat(desktop-ui): …` / `chore(desktop-ui): …` / `test(desktop-ui): …`. **NO `Co-Authored-By: Claude` / "authored by Claude" trailer.**
- Work on branch `phase-1-ui`. Run all `pnpm` commands from inside `desktop-ui/`. The mock brain runs from `protocol/`: `uv run uvicorn mock.server:app --port 8765`.

---

## File Structure

```
pnpm-workspace.yaml                  (NOT created — protocol/ stays standalone)
desktop-ui/
├── package.json                     scripts + deps (name @alfred/desktop-ui)
├── tsconfig.json                    strict; paths → ../protocol contract
├── tsconfig.node.json               for vite.config.ts
├── vite.config.ts                   react+tailwind plugins; aliases; /status proxy; vitest config
├── index.html                       Vite entry
├── src/
│   ├── main.tsx                     React root
│   ├── App.tsx                      HUD layout, wires store → components
│   ├── index.css                    Tailwind import + HUD theme tokens
│   ├── types/
│   │   └── schema.d.ts              ambient module for @alfred/protocol-schema
│   ├── test/
│   │   ├── setup.ts                 jest-dom matchers
│   │   └── fake-websocket.ts        injectable WebSocket double for client tests
│   ├── protocol/
│   │   ├── validator.ts             Ajv compile + validateMessage()
│   │   ├── client.ts                ProtocolClient
│   │   ├── status.ts                fetchStatus() + http transport
│   │   └── http.ts                  isTauri(), httpGet(), statusUrlFor()
│   ├── store/
│   │   ├── turns.ts                 pure Turn reducer (openTurn, applyMessage)
│   │   └── store.ts                 Zustand store wiring client + reducer + status
│   └── components/
│       ├── ConnectionBar.tsx
│       ├── EventStream.tsx
│       ├── CommandInput.tsx
│       ├── StatusPanel.tsx
│       ├── KillSwitch.tsx
│       ├── WireInspector.tsx
│       └── RiskBadge.tsx
└── src-tauri/                       (Task 12) Tauri v2 shell
    ├── Cargo.toml
    ├── build.rs
    ├── tauri.conf.json
    ├── capabilities/default.json
    └── src/main.rs
```

---

## Task 1: Scaffold `desktop-ui/` + contract wiring

**Files:**
- Create: `desktop-ui/package.json`, `desktop-ui/tsconfig.json`, `desktop-ui/tsconfig.node.json`, `desktop-ui/vite.config.ts`, `desktop-ui/index.html`, `desktop-ui/src/main.tsx`, `desktop-ui/src/App.tsx`, `desktop-ui/src/index.css`, `desktop-ui/src/types/schema.d.ts`, `desktop-ui/src/test/setup.ts`, `desktop-ui/src/smoke.test.ts`

**Interfaces:**
- Produces: a runnable Vite app and a green Vitest + `tsc --noEmit`. Establishes the `@alfred/protocol` and `@alfred/protocol-schema` aliases every later task relies on.

- [ ] **Step 1: Create `desktop-ui/package.json`**

```json
{
  "name": "@alfred/desktop-ui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "typecheck": "tsc --noEmit",
    "tauri": "tauri"
  }
}
```

- [ ] **Step 2: Install dependencies**

Run from `desktop-ui/`:

```bash
pnpm add react react-dom zustand ajv ajv-formats
pnpm add -D typescript vite @vitejs/plugin-react tailwindcss @tailwindcss/vite \
  vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event \
  @types/react @types/react-dom @types/node
```

Expected: a `desktop-ui/node_modules` and `desktop-ui/pnpm-lock.yaml` are created. `protocol/` is untouched.

- [ ] **Step 3: Create `desktop-ui/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "baseUrl": ".",
    "paths": {
      "@alfred/protocol": ["../protocol/gen/typescript/index.ts"]
    },
    "types": ["vitest/globals", "@testing-library/jest-dom", "node"]
  },
  "include": ["src", "vite.config.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Create `desktop-ui/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: Create `desktop-ui/vite.config.ts`**

```ts
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
      "/status": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

- [ ] **Step 6: Create `desktop-ui/src/types/schema.d.ts`**

```ts
declare module "@alfred/protocol-schema" {
  import type { AnySchema } from "ajv";
  const schema: AnySchema;
  export default schema;
}
```

- [ ] **Step 7: Create `desktop-ui/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ALFRED</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: Create `desktop-ui/src/index.css`**

```css
@import "tailwindcss";

@theme {
  --color-void: #04070d;
  --color-panel: #0a121f;
  --color-hud: #38e1ff;
  --color-hud-dim: #1a6c80;
  --color-amber: #ffb648;
  --color-danger: #ff5470;
  --color-safe: #5ef2a0;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
}

body {
  margin: 0;
  background: var(--color-void);
  color: var(--color-hud);
  font-family: var(--font-mono);
}
```

- [ ] **Step 9: Create `desktop-ui/src/App.tsx`**

```tsx
export default function App() {
  return <div className="p-6 text-hud">ALFRED online.</div>;
}
```

- [ ] **Step 10: Create `desktop-ui/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 11: Create `desktop-ui/src/test/setup.ts`**

```ts
import "@testing-library/jest-dom";
```

- [ ] **Step 12: Create `desktop-ui/src/smoke.test.ts` (proves the contract aliases resolve)**

```ts
import { describe, it, expect } from "vitest";
import type { Message } from "@alfred/protocol";
import schema from "@alfred/protocol-schema";

describe("contract wiring", () => {
  it("imports a protocol type and the schema", () => {
    const msg: Message = {
      v: 1,
      id: "t-1",
      ts: "2026-06-23T00:00:00Z",
      type: "status.request",
    };
    expect(msg.type).toBe("status.request");
    expect((schema as { title?: string }).title).toBe("Message");
  });
});
```

- [ ] **Step 13: Run the test and typecheck**

Run: `pnpm test && pnpm typecheck`
Expected: 1 passing test; `tsc --noEmit` exits 0.

- [ ] **Step 14: Commit**

```bash
git add desktop-ui
git commit -m "chore(desktop-ui): scaffold Vite+React+TS app wired to the frozen protocol"
```

---

## Task 2: Ajv validator

**Files:**
- Create: `desktop-ui/src/protocol/validator.ts`, `desktop-ui/src/protocol/validator.test.ts`

**Interfaces:**
- Produces:
  - `interface ValidationResult { valid: boolean; errors?: string }`
  - `function validateMessage(data: unknown): ValidationResult`

- [ ] **Step 1: Write the failing test**

`desktop-ui/src/protocol/validator.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { validateMessage } from "./validator";

describe("validateMessage", () => {
  it("accepts a well-formed message", () => {
    const r = validateMessage({
      v: 1,
      id: "x",
      ts: "2026-06-23T00:00:00Z",
      type: "command.submit",
      text: "hi",
      channel: "desktop",
    });
    expect(r.valid).toBe(true);
  });

  it("rejects a message with a bad timestamp", () => {
    const r = validateMessage({
      v: 1,
      id: "x",
      ts: "not-a-date",
      type: "command.submit",
      text: "hi",
      channel: "desktop",
    });
    expect(r.valid).toBe(false);
    expect(r.errors).toBeTruthy();
  });

  it("rejects a message with an unknown type", () => {
    const r = validateMessage({ v: 1, id: "x", ts: "2026-06-23T00:00:00Z", type: "nope" });
    expect(r.valid).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/protocol/validator.test.ts`
Expected: FAIL — cannot find module `./validator`.

- [ ] **Step 3: Write `desktop-ui/src/protocol/validator.ts`**

```ts
import { Ajv2020 } from "ajv/dist/2020.js";
import * as addFormatsModule from "ajv-formats";
import schema from "@alfred/protocol-schema";

const addFormats = addFormatsModule.default as unknown as (
  ajv: InstanceType<typeof Ajv2020>,
) => void;

const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

export interface ValidationResult {
  valid: boolean;
  errors?: string;
}

export function validateMessage(data: unknown): ValidationResult {
  const ok = validate(data) as boolean;
  if (ok) return { valid: true };
  return { valid: false, errors: ajv.errorsText(validate.errors) };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm exec vitest run src/protocol/validator.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add desktop-ui/src/protocol/validator.ts desktop-ui/src/protocol/validator.test.ts
git commit -m "feat(desktop-ui): Ajv validator compiled from the frozen schema"
```

---

## Task 3: ProtocolClient — connect, handshake, validated inbound, wire taps

**Files:**
- Create: `desktop-ui/src/test/fake-websocket.ts`, `desktop-ui/src/protocol/client.ts`, `desktop-ui/src/protocol/client.test.ts`

**Interfaces:**
- Consumes: `validateMessage` (Task 2); types from `@alfred/protocol`.
- Produces (relied on by Tasks 4, 7):
  - `type ConnectionPhase = "idle" | "connecting" | "handshaking" | "ready" | "reconnecting" | "closed" | "error"`
  - `interface ServerInfo { serverName: string; serverVersion: string; sessionId: string; protocolVersion: number }`
  - `interface PhaseEvent { phase: ConnectionPhase; server?: ServerInfo; error?: string }`
  - `interface WireEntry { entryId: string; direction: "in" | "out"; type: string; raw: unknown; valid: boolean; errors?: string; at: string }`
  - `class ProtocolClient` with `constructor(options: ProtocolClientOptions)`, `on(event, handler): () => void` for events `"phase" | "message" | "wire"`, `getPhase(): ConnectionPhase`, `connect(): void`, `disconnect(): void`. (Send helpers + reconnect arrive in Task 4.)
  - `interface ProtocolClientOptions { url: string; clientName?: string; clientVersion?: string; protocolVersion?: number; WebSocketCtor?: { new (url: string): WebSocket }; reconnect?: boolean; backoffBaseMs?: number; backoffMaxMs?: number }`

- [ ] **Step 1: Create the injectable fake WebSocket `desktop-ui/src/test/fake-websocket.ts`**

```ts
// Minimal WebSocket double matching the browser API surface ProtocolClient uses.
export class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  // --- test drivers ---
  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  receive(msg: unknown): void {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  receiveRaw(data: string): void {
    this.onmessage?.({ data });
  }
  serverClose(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  // --- WebSocket API used by the client ---
  send(data: string): void {
    this.sent.push(data);
  }
  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
}

export function lastSocket(): FakeWebSocket {
  const s = FakeWebSocket.instances.at(-1);
  if (!s) throw new Error("no FakeWebSocket created");
  return s;
}

export function resetSockets(): void {
  FakeWebSocket.instances = [];
}
```

- [ ] **Step 2: Write the failing test `desktop-ui/src/protocol/client.test.ts`**

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { ProtocolClient } from "./client";
import type { PhaseEvent, WireEntry } from "./client";
import { FakeWebSocket, lastSocket, resetSockets } from "../test/fake-websocket";

function makeClient() {
  return new ProtocolClient({
    url: "ws://127.0.0.1:8765/ws",
    WebSocketCtor: FakeWebSocket as unknown as { new (url: string): WebSocket },
    reconnect: false,
  });
}

const serverHello = {
  v: 1,
  id: "s-1",
  ts: "2026-06-23T00:00:00Z",
  type: "server.hello",
  corr: "ui-1-0",
  server_name: "alfred-mock-brain",
  server_version: "0.1.0",
  protocol_version: 1,
  session_id: "mock-session",
};

describe("ProtocolClient handshake", () => {
  beforeEach(() => resetSockets());

  it("sends client.hello on open and goes ready on server.hello", () => {
    const phases: PhaseEvent[] = [];
    const client = makeClient();
    client.on("phase", (e) => phases.push(e));
    client.connect();

    const ws = lastSocket();
    expect(phases.at(-1)?.phase).toBe("connecting");
    ws.open();
    expect(phases.at(-1)?.phase).toBe("handshaking");

    const sent = JSON.parse(ws.sent[0]);
    expect(sent.type).toBe("client.hello");
    expect(sent.protocol_version).toBe(1);
    expect(sent.client_name).toBe("alfred-desktop-ui");

    ws.receive(serverHello);
    const ready = phases.at(-1);
    expect(ready?.phase).toBe("ready");
    expect(ready?.server?.sessionId).toBe("mock-session");
  });

  it("emits validated inbound messages and logs them to the wire", () => {
    const messages: string[] = [];
    const wire: WireEntry[] = [];
    const client = makeClient();
    client.on("message", (m) => messages.push(m.type));
    client.on("wire", (w) => wire.push(w));
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive(serverHello);

    expect(messages).toContain("server.hello");
    const inHello = wire.find((w) => w.direction === "in" && w.type === "server.hello");
    expect(inHello?.valid).toBe(true);
  });

  it("rejects a schema-invalid inbound message and enters error", () => {
    const phases: PhaseEvent[] = [];
    const messages: string[] = [];
    const client = makeClient();
    client.on("phase", (e) => phases.push(e));
    client.on("message", (m) => messages.push(m.type));
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive({ v: 1, id: "bad", ts: "nope", type: "server.hello" });

    expect(phases.at(-1)?.phase).toBe("error");
    expect(messages).not.toContain("server.hello");
  });

  it("enters error on an unsupported_version error", () => {
    const phases: PhaseEvent[] = [];
    const client = makeClient();
    client.on("phase", (e) => phases.push(e));
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive({
      v: 1,
      id: "e-1",
      ts: "2026-06-23T00:00:00Z",
      type: "error",
      code: "unsupported_version",
      message: "This server speaks protocol v2.",
    });
    expect(phases.at(-1)?.phase).toBe("error");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pnpm exec vitest run src/protocol/client.test.ts`
Expected: FAIL — cannot find module `./client`.

- [ ] **Step 4: Write `desktop-ui/src/protocol/client.ts`**

```ts
import type { Message, ServerHello } from "@alfred/protocol";
import { validateMessage } from "./validator";

export type ConnectionPhase =
  | "idle"
  | "connecting"
  | "handshaking"
  | "ready"
  | "reconnecting"
  | "closed"
  | "error";

export interface ServerInfo {
  serverName: string;
  serverVersion: string;
  sessionId: string;
  protocolVersion: number;
}

export interface PhaseEvent {
  phase: ConnectionPhase;
  server?: ServerInfo;
  error?: string;
}

export interface WireEntry {
  entryId: string;
  direction: "in" | "out";
  type: string;
  raw: unknown;
  valid: boolean;
  errors?: string;
  at: string;
}

export interface ProtocolClientOptions {
  url: string;
  clientName?: string;
  clientVersion?: string;
  protocolVersion?: number;
  WebSocketCtor?: { new (url: string): WebSocket };
  reconnect?: boolean;
  backoffBaseMs?: number;
  backoffMaxMs?: number;
}

interface EventMap {
  phase: (e: PhaseEvent) => void;
  message: (m: Message) => void;
  wire: (w: WireEntry) => void;
}

let counter = 0;
function uid(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter}-${Math.floor(Math.random() * 1_000_000)}`;
}

export class ProtocolClient {
  protected ws: WebSocket | null = null;
  private phase: ConnectionPhase = "idle";
  private readonly handlers: { [K in keyof EventMap]: Set<EventMap[K]> } = {
    phase: new Set(),
    message: new Set(),
    wire: new Set(),
  };

  protected readonly url: string;
  protected readonly clientName: string;
  protected readonly clientVersion: string;
  protected readonly protocolVersion: number;
  protected readonly WebSocketCtor: { new (url: string): WebSocket };
  protected readonly reconnect: boolean;
  protected readonly backoffBaseMs: number;
  protected readonly backoffMaxMs: number;

  constructor(options: ProtocolClientOptions) {
    this.url = options.url;
    this.clientName = options.clientName ?? "alfred-desktop-ui";
    this.clientVersion = options.clientVersion ?? "0.1.0";
    this.protocolVersion = options.protocolVersion ?? 1;
    this.WebSocketCtor = options.WebSocketCtor ?? WebSocket;
    this.reconnect = options.reconnect ?? true;
    this.backoffBaseMs = options.backoffBaseMs ?? 500;
    this.backoffMaxMs = options.backoffMaxMs ?? 8000;
  }

  on<K extends keyof EventMap>(event: K, handler: EventMap[K]): () => void {
    this.handlers[event].add(handler);
    return () => {
      this.handlers[event].delete(handler);
    };
  }

  protected emit<K extends keyof EventMap>(
    event: K,
    ...args: Parameters<EventMap[K]>
  ): void {
    for (const h of this.handlers[event]) {
      (h as (...a: Parameters<EventMap[K]>) => void)(...args);
    }
  }

  getPhase(): ConnectionPhase {
    return this.phase;
  }

  protected setPhase(phase: ConnectionPhase, extra: Omit<PhaseEvent, "phase"> = {}): void {
    this.phase = phase;
    this.emit("phase", { phase, ...extra });
  }

  connect(): void {
    this.openSocket("connecting");
  }

  protected openSocket(initialPhase: ConnectionPhase): void {
    this.setPhase(initialPhase);
    const ws = new this.WebSocketCtor(this.url);
    this.ws = ws;
    ws.onopen = () => this.onOpen();
    ws.onmessage = (ev: MessageEvent) => this.handleInbound(ev.data);
    ws.onerror = () => this.setPhase("error", { error: "socket error" });
    ws.onclose = () => this.onClose();
  }

  protected onOpen(): void {
    this.setPhase("handshaking");
    this.sendMessage({
      ...this.envelope(),
      type: "client.hello",
      client_name: this.clientName,
      client_version: this.clientVersion,
      protocol_version: this.protocolVersion,
    });
  }

  // Overridden in Task 4 to schedule reconnects.
  protected onClose(): void {
    this.ws = null;
    this.setPhase("closed");
  }

  protected handleInbound(data: unknown): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(typeof data === "string" ? data : String(data));
    } catch {
      this.logWire("in", "?", data, { valid: false, errors: "invalid JSON" });
      this.setPhase("error", { error: "received a non-JSON frame" });
      return;
    }
    const result = validateMessage(parsed);
    const type = (parsed as { type?: string }).type ?? "?";
    this.logWire("in", type, parsed, result);
    if (!result.valid) {
      this.setPhase("error", { error: `invalid inbound ${type}: ${result.errors}` });
      return;
    }
    const msg = parsed as Message;
    this.onValidMessage(msg);
    this.emit("message", msg);
  }

  protected onValidMessage(msg: Message): void {
    if (msg.type === "server.hello") {
      const hello = msg as ServerHello;
      this.setPhase("ready", {
        server: {
          serverName: hello.server_name,
          serverVersion: hello.server_version,
          sessionId: hello.session_id,
          protocolVersion: hello.protocol_version,
        },
      });
    } else if (msg.type === "error" && msg.code === "unsupported_version") {
      this.setPhase("error", { error: msg.message });
    }
  }

  disconnect(): void {
    this.ws?.close();
  }

  protected envelope(): { v: 1; id: string; ts: string } {
    return { v: 1, id: uid("ui"), ts: new Date().toISOString() };
  }

  protected sendMessage(msg: Message): void {
    const result = validateMessage(msg);
    this.logWire("out", msg.type, msg, result);
    this.ws?.send(JSON.stringify(msg));
  }

  protected logWire(
    direction: "in" | "out",
    type: string,
    raw: unknown,
    result: { valid: boolean; errors?: string },
  ): void {
    this.emit("wire", {
      entryId: uid("wire"),
      direction,
      type,
      raw,
      valid: result.valid,
      errors: result.errors,
      at: new Date().toISOString(),
    });
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm exec vitest run src/protocol/client.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add desktop-ui/src/protocol/client.ts desktop-ui/src/protocol/client.test.ts desktop-ui/src/test/fake-websocket.ts
git commit -m "feat(desktop-ui): ProtocolClient handshake + validated inbound + wire taps"
```

---

## Task 4: ProtocolClient — send helpers + reconnect

**Files:**
- Modify: `desktop-ui/src/protocol/client.ts`
- Create/extend test: `desktop-ui/src/protocol/client.send.test.ts`

**Interfaces:**
- Produces (relied on by Task 7):
  - `submitCommand(text: string, opts?: { scopeOverride?: string }): string` — returns the generated message `id` (the turn's `corr`).
  - `activateKillSwitch(reason?: string): string` — returns the generated message `id`.
  - Reconnect with exponential backoff when `reconnect` is true and the close was not caller-initiated; re-runs the handshake on reopen.

- [ ] **Step 1: Write the failing test `desktop-ui/src/protocol/client.send.test.ts`**

```ts
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { ProtocolClient } from "./client";
import { FakeWebSocket, lastSocket, resetSockets } from "../test/fake-websocket";

const Ctor = FakeWebSocket as unknown as { new (url: string): WebSocket };
const serverHello = {
  v: 1, id: "s-1", ts: "2026-06-23T00:00:00Z", type: "server.hello",
  corr: "ui-1-0", server_name: "m", server_version: "0.1.0",
  protocol_version: 1, session_id: "sess",
};

describe("ProtocolClient send helpers", () => {
  beforeEach(() => resetSockets());

  it("submitCommand emits a valid command.submit and returns its id", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: false });
    client.connect();
    const ws = lastSocket();
    ws.open();
    ws.receive(serverHello);
    const id = client.submitCommand("check the build", { scopeOverride: "coding" });
    const sent = JSON.parse(ws.sent.at(-1)!);
    expect(sent.type).toBe("command.submit");
    expect(sent.id).toBe(id);
    expect(sent.channel).toBe("desktop");
    expect(sent.text).toBe("check the build");
    expect(sent.scope_override).toBe("coding");
  });

  it("omits scope_override when absent (never null)", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: false });
    client.connect();
    const ws = lastSocket();
    ws.open();
    client.submitCommand("hello");
    const sent = JSON.parse(ws.sent.at(-1)!);
    expect("scope_override" in sent).toBe(false);
  });

  it("activateKillSwitch emits a valid kill_switch.activate", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: false });
    client.connect();
    const ws = lastSocket();
    ws.open();
    client.activateKillSwitch("panic");
    const sent = JSON.parse(ws.sent.at(-1)!);
    expect(sent.type).toBe("kill_switch.activate");
    expect(sent.channel).toBe("desktop");
    expect(sent.reason).toBe("panic");
  });
});

describe("ProtocolClient reconnect", () => {
  beforeEach(() => {
    resetSockets();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("reconnects with backoff after an unexpected close", () => {
    const client = new ProtocolClient({
      url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: true, backoffBaseMs: 100,
    });
    client.connect();
    lastSocket().open();
    const firstSocket = lastSocket();
    firstSocket.serverClose();
    expect(client.getPhase()).toBe("reconnecting");
    vi.advanceTimersByTime(100);
    expect(FakeWebSocket.instances.length).toBe(2);
  });

  it("does not reconnect after disconnect()", () => {
    const client = new ProtocolClient({ url: "ws://x/ws", WebSocketCtor: Ctor, reconnect: true });
    client.connect();
    lastSocket().open();
    client.disconnect();
    vi.advanceTimersByTime(10000);
    expect(FakeWebSocket.instances.length).toBe(1);
    expect(client.getPhase()).toBe("closed");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/protocol/client.send.test.ts`
Expected: FAIL — `submitCommand` is not a function.

- [ ] **Step 3: Add fields, send helpers, and reconnect to `client.ts`**

Add these private fields next to the other `protected readonly` fields:

```ts
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manuallyClosed = false;
```

Replace `connect()` and `onClose()`, and replace `disconnect()`, with:

```ts
  connect(): void {
    this.manuallyClosed = false;
    this.reconnectAttempts = 0;
    this.openSocket("connecting");
  }

  protected onClose(): void {
    this.ws = null;
    if (this.manuallyClosed || !this.reconnect) {
      this.setPhase("closed");
      return;
    }
    const delay = Math.min(
      this.backoffMaxMs,
      this.backoffBaseMs * 2 ** this.reconnectAttempts,
    );
    this.reconnectAttempts += 1;
    this.setPhase("reconnecting");
    this.reconnectTimer = setTimeout(() => this.openSocket("reconnecting"), delay);
  }

  disconnect(): void {
    this.manuallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
  }
```

Reset `reconnectAttempts` to 0 inside `onValidMessage` when a `server.hello` arrives — change that branch to:

```ts
    if (msg.type === "server.hello") {
      const hello = msg as ServerHello;
      this.reconnectAttempts = 0;
      this.setPhase("ready", {
        server: {
          serverName: hello.server_name,
          serverVersion: hello.server_version,
          sessionId: hello.session_id,
          protocolVersion: hello.protocol_version,
        },
      });
    } else if (msg.type === "error" && msg.code === "unsupported_version") {
```

Add the send helpers (after `disconnect()`):

```ts
  submitCommand(text: string, opts: { scopeOverride?: string } = {}): string {
    const msg: Message = {
      ...this.envelope(),
      type: "command.submit",
      text,
      channel: "desktop",
      ...(opts.scopeOverride ? { scope_override: opts.scopeOverride } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }

  activateKillSwitch(reason?: string): string {
    const msg: Message = {
      ...this.envelope(),
      type: "kill_switch.activate",
      channel: "desktop",
      ...(reason ? { reason } : {}),
    };
    this.sendMessage(msg);
    return msg.id;
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm exec vitest run src/protocol/client.send.test.ts && pnpm exec vitest run src/protocol/client.test.ts`
Expected: PASS (send: 5 tests; handshake: 4 tests).

- [ ] **Step 5: Commit**

```bash
git add desktop-ui/src/protocol/client.ts desktop-ui/src/protocol/client.send.test.ts
git commit -m "feat(desktop-ui): command/kill-switch send helpers + reconnect backoff"
```

---

## Task 5: Turn reducer

**Files:**
- Create: `desktop-ui/src/store/turns.ts`, `desktop-ui/src/store/turns.test.ts`

**Interfaces:**
- Consumes: types from `@alfred/protocol`.
- Produces (relied on by Task 7):
  - `interface Turn { corr: string; commandText: string; channel: "desktop"; scopeOverride?: string; ack?: { accepted: boolean; reason?: string }; thoughts: string[]; actions: TurnAction[]; message: { text: string; final: boolean }; status?: "completed" | "error" | "killed"; startedAt: string; endedAt?: string }`
  - `interface TurnAction { tool: string; summary: string; risk: "safe" | "sensitive" | "forbidden" }`
  - `function openTurn(turns: Turn[], params: { corr: string; commandText: string; scopeOverride?: string; at: string }): Turn[]`
  - `function applyMessage(turns: Turn[], msg: Message): Turn[]`

- [ ] **Step 1: Write the failing test `desktop-ui/src/store/turns.test.ts`**

```ts
import { describe, it, expect } from "vitest";
import { openTurn, applyMessage } from "./turns";
import type { Message } from "@alfred/protocol";

function start() {
  return openTurn([], { corr: "c1", commandText: "check the build", at: "2026-06-23T00:00:00Z" });
}

const msg = (m: Partial<Message> & { type: string }): Message =>
  ({ v: 1, id: "m", ts: "2026-06-23T00:00:00Z", ...m } as Message);

describe("turn reducer", () => {
  it("opens a turn", () => {
    const turns = start();
    expect(turns).toHaveLength(1);
    expect(turns[0].corr).toBe("c1");
    expect(turns[0].message.text).toBe("");
  });

  it("records ack, thought, and action by corr", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "command.ack", corr: "c1", accepted: true }));
    turns = applyMessage(turns, msg({ type: "agent.thought", corr: "c1", text: "thinking" }));
    turns = applyMessage(
      turns,
      msg({ type: "agent.action", corr: "c1", tool: "shell", summary: "run build", risk: "sensitive" }),
    );
    expect(turns[0].ack?.accepted).toBe(true);
    expect(turns[0].thoughts).toEqual(["thinking"]);
    expect(turns[0].actions[0]).toEqual({ tool: "shell", summary: "run build", risk: "sensitive" });
  });

  it("assembles streamed message chunks until final", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "agent.message", corr: "c1", text: "The build is ", final: false }));
    turns = applyMessage(turns, msg({ type: "agent.message", corr: "c1", text: "green, sir.", final: true }));
    expect(turns[0].message.text).toBe("The build is green, sir.");
    expect(turns[0].message.final).toBe(true);
  });

  it("records turn_complete status", () => {
    let turns = start();
    turns = applyMessage(turns, msg({ type: "agent.turn_complete", corr: "c1", status: "completed" }));
    expect(turns[0].status).toBe("completed");
  });

  it("ignores messages for unknown corr without throwing", () => {
    const turns = start();
    const next = applyMessage(turns, msg({ type: "agent.thought", corr: "nope", text: "x" }));
    expect(next[0].thoughts).toHaveLength(0);
  });

  it("ignores non-turn messages", () => {
    const turns = start();
    const next = applyMessage(turns, msg({ type: "status.request" }));
    expect(next).toEqual(turns);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/store/turns.test.ts`
Expected: FAIL — cannot find module `./turns`.

- [ ] **Step 3: Write `desktop-ui/src/store/turns.ts`**

```ts
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
  status?: "completed" | "error" | "killed";
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm exec vitest run src/store/turns.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add desktop-ui/src/store/turns.ts desktop-ui/src/store/turns.test.ts
git commit -m "feat(desktop-ui): pure turn reducer (open/route by corr, chunk assembly)"
```

---

## Task 6: HTTP transport + fetchStatus

**Files:**
- Create: `desktop-ui/src/protocol/http.ts`, `desktop-ui/src/protocol/status.ts`, `desktop-ui/src/protocol/status.test.ts`

**Interfaces:**
- Consumes: `validateMessage` (Task 2); `StatusResponse` from `@alfred/protocol`.
- Produces (relied on by Task 7):
  - `function isTauri(): boolean`
  - `function statusUrlFor(baseUrl: string): string` — `${baseUrl}/status` under Tauri, else `/status` (uses the Vite dev proxy).
  - `type HttpGet = (url: string) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>`
  - `async function fetchStatus(baseUrl: string, deps?: { get?: HttpGet; tauri?: boolean }): Promise<StatusResponse>`

- [ ] **Step 1: Write the failing test `desktop-ui/src/protocol/status.test.ts`**

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/protocol/status.test.ts`
Expected: FAIL — cannot find module `./status`.

- [ ] **Step 3: Write `desktop-ui/src/protocol/http.ts`**

```ts
export function isTauri(): boolean {
  return (
    typeof window !== "undefined" &&
    ("__TAURI_INTERNALS__" in window || "__TAURI__" in window)
  );
}

export interface HttpResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

export type HttpGet = (url: string) => Promise<HttpResponse>;

// In Tauri, route through the HTTP plugin to bypass webview CORS; in a plain
// browser, use the global fetch (same-origin path goes through the Vite proxy).
export async function defaultGet(url: string): Promise<HttpResponse> {
  if (isTauri()) {
    const { fetch: tauriFetch } = await import("@tauri-apps/plugin-http");
    const res = await tauriFetch(url, { method: "GET" });
    return { ok: res.ok, status: res.status, json: () => res.json() };
  }
  const res = await fetch(url, { method: "GET" });
  return { ok: res.ok, status: res.status, json: () => res.json() };
}

export function statusUrlFor(baseUrl: string): string {
  return isTauri() ? `${baseUrl}/status` : "/status";
}
```

Note: the `@tauri-apps/plugin-http` import is dynamic, so it is only resolved when running inside Tauri. It is added as a dependency in Task 12; until then, browser/test paths never reach it.

- [ ] **Step 4: Write `desktop-ui/src/protocol/status.ts`**

```ts
import type { StatusResponse } from "@alfred/protocol";
import { validateMessage } from "./validator";
import { defaultGet, statusUrlFor, type HttpGet } from "./http";

export { statusUrlFor };

export async function fetchStatus(
  baseUrl: string,
  deps: { get?: HttpGet; tauri?: boolean } = {},
): Promise<StatusResponse> {
  const get = deps.get ?? defaultGet;
  const url = deps.tauri ? `${baseUrl}/status` : statusUrlFor(baseUrl);
  const res = await get(url);
  if (!res.ok) throw new Error(`status request failed: HTTP ${res.status}`);
  const body = await res.json();
  const result = validateMessage(body);
  if (!result.valid) throw new Error(`invalid status.response: ${result.errors}`);
  return body as StatusResponse;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm exec vitest run src/protocol/status.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add desktop-ui/src/protocol/http.ts desktop-ui/src/protocol/status.ts desktop-ui/src/protocol/status.test.ts
git commit -m "feat(desktop-ui): fetchStatus over Tauri-http/proxy with schema validation"
```

---

## Task 7: Zustand store

**Files:**
- Create: `desktop-ui/src/store/store.ts`, `desktop-ui/src/store/store.test.ts`

**Interfaces:**
- Consumes: `ProtocolClient` (Tasks 3–4), turn reducer (Task 5), `fetchStatus` (Task 6).
- Produces (relied on by Tasks 8–10): a Zustand hook `useStore` with state:
  - `phase: ConnectionPhase`, `server?: ServerInfo`, `lastError?: string`
  - `url: string` (default `"ws://127.0.0.1:8765/ws"`), `baseUrl: string` (default `"http://127.0.0.1:8765"`)
  - `turns: Turn[]`, `status?: StatusResponse`, `statusError?: string`, `wire: WireEntry[]`
  - actions: `setUrl(url: string)`, `setBaseUrl(url: string)`, `connect()`, `disconnect()`, `submit(text: string, scopeOverride?: string)`, `kill(reason?: string)`, `refreshStatus()`
  - test seam: `createStore(opts: { clientFactory?: (url: string) => ProtocolClient; statusFn?: typeof fetchStatus })` returning the same hook, for injecting a `FakeWebSocket`-backed client.

- [ ] **Step 1: Write the failing test `desktop-ui/src/store/store.test.ts`**

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { createStore } from "./store";
import { ProtocolClient } from "../protocol/client";
import { FakeWebSocket, lastSocket, resetSockets } from "../test/fake-websocket";

const Ctor = FakeWebSocket as unknown as { new (url: string): WebSocket };

function makeStore() {
  return createStore({
    clientFactory: (url) =>
      new ProtocolClient({ url, WebSocketCtor: Ctor, reconnect: false }),
    statusFn: async () => ({
      v: 1, id: "s", ts: "2026-06-23T00:00:00Z", type: "status.response",
      corr: "http-status", uptime_seconds: 1, server_version: "0.1.0",
      active_scopes: ["coding"], busy: false,
    }),
  });
}

const serverHello = {
  v: 1, id: "s-1", ts: "2026-06-23T00:00:00Z", type: "server.hello",
  corr: "ui-1-0", server_name: "m", server_version: "0.1.0",
  protocol_version: 1, session_id: "sess",
};

describe("store", () => {
  beforeEach(() => resetSockets());

  it("connects and reaches ready", () => {
    const useStore = makeStore();
    useStore.getState().connect();
    lastSocket().open();
    lastSocket().receive(serverHello);
    expect(useStore.getState().phase).toBe("ready");
    expect(useStore.getState().server?.sessionId).toBe("sess");
  });

  it("opens a turn on submit and routes the brain's reply", () => {
    const useStore = makeStore();
    useStore.getState().connect();
    const ws = lastSocket();
    ws.open();
    ws.receive(serverHello);
    useStore.getState().submit("check the build");
    const corr = useStore.getState().turns[0].corr;
    ws.receive({ v: 1, id: "a", ts: "2026-06-23T00:00:00Z", type: "agent.message", corr, text: "done.", final: true });
    expect(useStore.getState().turns[0].message.text).toBe("done.");
  });

  it("records wire entries", () => {
    const useStore = makeStore();
    useStore.getState().connect();
    lastSocket().open();
    lastSocket().receive(serverHello);
    expect(useStore.getState().wire.length).toBeGreaterThan(0);
  });

  it("refreshStatus stores the response", async () => {
    const useStore = makeStore();
    await useStore.getState().refreshStatus();
    expect(useStore.getState().status?.active_scopes).toEqual(["coding"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/store/store.test.ts`
Expected: FAIL — cannot find module `./store`.

- [ ] **Step 3: Write `desktop-ui/src/store/store.ts`**

```ts
import { create, type StoreApi, type UseBoundStore } from "zustand";
import type { StatusResponse } from "@alfred/protocol";
import {
  ProtocolClient,
  type ConnectionPhase,
  type ServerInfo,
  type WireEntry,
} from "../protocol/client";
import { fetchStatus } from "../protocol/status";
import { openTurn, applyMessage, type Turn } from "./turns";

const WIRE_LIMIT = 500;

export interface AppState {
  phase: ConnectionPhase;
  server?: ServerInfo;
  lastError?: string;
  url: string;
  baseUrl: string;
  turns: Turn[];
  status?: StatusResponse;
  statusError?: string;
  wire: WireEntry[];
  setUrl: (url: string) => void;
  setBaseUrl: (url: string) => void;
  connect: () => void;
  disconnect: () => void;
  submit: (text: string, scopeOverride?: string) => void;
  kill: (reason?: string) => void;
  refreshStatus: () => Promise<void>;
}

interface StoreDeps {
  clientFactory?: (url: string) => ProtocolClient;
  statusFn?: typeof fetchStatus;
}

export function createStore(
  deps: StoreDeps = {},
): UseBoundStore<StoreApi<AppState>> {
  const clientFactory = deps.clientFactory ?? ((url) => new ProtocolClient({ url }));
  const statusFn = deps.statusFn ?? fetchStatus;
  let client: ProtocolClient | null = null;

  return create<AppState>((set, get) => ({
    phase: "idle",
    url: "ws://127.0.0.1:8765/ws",
    baseUrl: "http://127.0.0.1:8765",
    turns: [],
    wire: [],

    setUrl: (url) => set({ url }),
    setBaseUrl: (baseUrl) => set({ baseUrl }),

    connect: () => {
      client?.disconnect();
      const c = clientFactory(get().url);
      client = c;
      c.on("phase", (e) =>
        set({ phase: e.phase, server: e.server ?? get().server, lastError: e.error }),
      );
      c.on("message", (m) => set({ turns: applyMessage(get().turns, m) }));
      c.on("wire", (w) => set({ wire: [...get().wire, w].slice(-WIRE_LIMIT) }));
      c.connect();
    },

    disconnect: () => client?.disconnect(),

    submit: (text, scopeOverride) => {
      if (!client) return;
      const corr = client.submitCommand(text, scopeOverride ? { scopeOverride } : {});
      set({
        turns: openTurn(get().turns, {
          corr,
          commandText: text,
          ...(scopeOverride ? { scopeOverride } : {}),
          at: new Date().toISOString(),
        }),
      });
    },

    kill: (reason) => client?.activateKillSwitch(reason),

    refreshStatus: async () => {
      try {
        const status = await statusFn(get().baseUrl);
        set({ status, statusError: undefined });
      } catch (err) {
        set({ statusError: err instanceof Error ? err.message : String(err) });
      }
    },
  }));
}

export const useStore = createStore();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm exec vitest run src/store/store.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add desktop-ui/src/store/store.ts desktop-ui/src/store/store.test.ts
git commit -m "feat(desktop-ui): Zustand store wiring client, turns, and status"
```

---

## Task 8: App shell + ConnectionBar + EventStream + CommandInput

**Files:**
- Create: `desktop-ui/src/components/RiskBadge.tsx`, `desktop-ui/src/components/ConnectionBar.tsx`, `desktop-ui/src/components/EventStream.tsx`, `desktop-ui/src/components/CommandInput.tsx`, `desktop-ui/src/components/CommandInput.test.tsx`
- Modify: `desktop-ui/src/App.tsx`

**Interfaces:**
- Consumes: `useStore` (Task 7), `Turn`/`TurnAction` (Task 5).
- Produces: a browser-runnable dashboard (connection + live stream + command input).

- [ ] **Step 1: Write the failing test `desktop-ui/src/components/CommandInput.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommandInput } from "./CommandInput";
import { useStore } from "../store/store";

describe("CommandInput", () => {
  beforeEach(() => useStore.setState({ phase: "ready", turns: [] }));

  it("submits the typed command via the store", async () => {
    const submit = vi.fn();
    useStore.setState({ submit });
    render(<CommandInput />);
    await userEvent.type(screen.getByPlaceholderText(/command/i), "check the build");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(submit).toHaveBeenCalledWith("check the build", undefined);
  });

  it("is disabled when not ready", () => {
    useStore.setState({ phase: "idle" });
    render(<CommandInput />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/components/CommandInput.test.tsx`
Expected: FAIL — cannot find module `./CommandInput`.

- [ ] **Step 3: Write `desktop-ui/src/components/RiskBadge.tsx`**

```tsx
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
```

- [ ] **Step 4: Write `desktop-ui/src/components/CommandInput.tsx`**

```tsx
import { useState } from "react";
import { useStore } from "../store/store";

export function CommandInput() {
  const phase = useStore((s) => s.phase);
  const submit = useStore((s) => s.submit);
  const [text, setText] = useState("");
  const [scope, setScope] = useState("");
  const ready = phase === "ready";

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed || !ready) return;
    submit(trimmed, scope.trim() || undefined);
    setText("");
  };

  return (
    <div className="flex gap-2 border-t border-hud-dim/30 bg-panel/60 p-3">
      <input
        className="w-32 rounded bg-void px-2 py-1 text-xs text-hud-dim outline-none placeholder:text-hud-dim/50"
        placeholder="scope (optional)"
        value={scope}
        onChange={(e) => setScope(e.target.value)}
      />
      <input
        className="flex-1 rounded bg-void px-3 py-1 text-sm text-hud outline-none placeholder:text-hud-dim/60"
        placeholder="Issue a command, sir…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && send()}
      />
      <button
        className="rounded border border-hud px-4 py-1 text-sm uppercase tracking-wide text-hud disabled:opacity-30"
        onClick={send}
        disabled={!ready}
      >
        Send
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Write `desktop-ui/src/components/ConnectionBar.tsx`**

```tsx
import { useStore } from "../store/store";

const DOT: Record<string, string> = {
  ready: "bg-safe",
  connecting: "bg-amber",
  handshaking: "bg-amber",
  reconnecting: "bg-amber",
  idle: "bg-hud-dim",
  closed: "bg-hud-dim",
  error: "bg-danger",
};

export function ConnectionBar() {
  const { phase, url, server, setUrl, connect, disconnect, lastError } = useStore();
  const connected = phase === "ready";

  return (
    <header className="flex items-center gap-3 border-b border-hud-dim/30 bg-panel/80 px-4 py-2">
      <span className={`h-3 w-3 animate-pulse rounded-full ${DOT[phase] ?? "bg-hud-dim"}`} />
      <span className="text-lg font-bold tracking-[0.3em] text-hud">ALFRED</span>
      <input
        className="w-72 rounded bg-void px-2 py-1 text-xs text-hud-dim outline-none"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        disabled={connected}
      />
      <button
        className="rounded border border-hud px-3 py-1 text-xs uppercase text-hud"
        onClick={connected ? disconnect : connect}
      >
        {connected ? "Disconnect" : "Connect"}
      </button>
      <span className="ml-auto text-xs text-hud-dim">
        {server ? `${server.serverName} v${server.serverVersion} · ${server.sessionId}` : phase}
        {lastError ? ` · ${lastError}` : ""}
      </span>
    </header>
  );
}
```

- [ ] **Step 6: Write `desktop-ui/src/components/EventStream.tsx`**

```tsx
import { useStore } from "../store/store";
import { RiskBadge } from "./RiskBadge";
import type { Turn } from "../store/turns";

function TurnCard({ turn }: { turn: Turn }) {
  return (
    <div className="rounded border border-hud-dim/20 bg-panel/40 p-3">
      <div className="mb-2 text-sm text-hud">
        <span className="text-hud-dim">❯ </span>
        {turn.commandText}
        {turn.status && (
          <span className="ml-2 text-[10px] uppercase text-hud-dim">[{turn.status}]</span>
        )}
      </div>
      {turn.thoughts.map((t, i) => (
        <div key={`th-${i}`} className="pl-4 text-xs italic text-hud-dim">
          ⋯ {t}
        </div>
      ))}
      {turn.actions.map((a, i) => (
        <div key={`ac-${i}`} className="flex items-center gap-2 pl-4 text-xs text-hud">
          <RiskBadge risk={a.risk} />
          <span className="text-hud-dim">{a.tool}</span>
          <span>{a.summary}</span>
        </div>
      ))}
      {turn.message.text && (
        <div className="mt-2 pl-4 text-sm text-hud [text-shadow:0_0_8px_var(--color-hud)]">
          {turn.message.text}
        </div>
      )}
    </div>
  );
}

export function EventStream() {
  const turns = useStore((s) => s.turns);
  return (
    <main className="flex-1 space-y-3 overflow-y-auto p-4">
      {turns.length === 0 ? (
        <p className="text-sm text-hud-dim">
          Awaiting instruction. I do hope it's worth my processing cycles.
        </p>
      ) : (
        turns.map((t) => <TurnCard key={t.corr} turn={t} />)
      )}
    </main>
  );
}
```

- [ ] **Step 7: Replace `desktop-ui/src/App.tsx`**

```tsx
import { ConnectionBar } from "./components/ConnectionBar";
import { EventStream } from "./components/EventStream";
import { CommandInput } from "./components/CommandInput";

export default function App() {
  return (
    <div className="flex h-screen flex-col bg-void text-hud">
      <ConnectionBar />
      <EventStream />
      <CommandInput />
    </div>
  );
}
```

- [ ] **Step 8: Run the test and typecheck**

Run: `pnpm exec vitest run src/components/CommandInput.test.tsx && pnpm typecheck`
Expected: PASS (2 tests); `tsc --noEmit` exits 0.

- [ ] **Step 9: Manual smoke check against the mock brain**

In `protocol/`: `uv run uvicorn mock.server:app --port 8765`.
In `desktop-ui/`: `pnpm dev`, open the printed URL, click **Connect**, send "check the build", and confirm the thought/action/streamed reply render.

- [ ] **Step 10: Commit**

```bash
git add desktop-ui/src/App.tsx desktop-ui/src/components
git commit -m "feat(desktop-ui): dashboard shell, connection bar, event stream, command input"
```

---

## Task 9: StatusPanel + KillSwitch

**Files:**
- Create: `desktop-ui/src/components/StatusPanel.tsx`, `desktop-ui/src/components/KillSwitch.tsx`, `desktop-ui/src/components/KillSwitch.test.tsx`
- Modify: `desktop-ui/src/App.tsx`

**Interfaces:**
- Consumes: `useStore` (`status`, `refreshStatus`, `kill`, `phase`).
- Produces: a status panel (polls `/status`) and an always-reachable kill switch with an unambiguous confirm.

- [ ] **Step 1: Write the failing test `desktop-ui/src/components/KillSwitch.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KillSwitch } from "./KillSwitch";
import { useStore } from "../store/store";

describe("KillSwitch", () => {
  beforeEach(() => useStore.setState({ phase: "ready" }));

  it("requires confirmation, then calls kill", async () => {
    const kill = vi.fn();
    useStore.setState({ kill });
    render(<KillSwitch />);
    await userEvent.click(screen.getByRole("button", { name: /kill switch/i }));
    expect(kill).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /^confirm halt$/i }));
    expect(kill).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/components/KillSwitch.test.tsx`
Expected: FAIL — cannot find module `./KillSwitch`.

- [ ] **Step 3: Write `desktop-ui/src/components/KillSwitch.tsx`**

```tsx
import { useState } from "react";
import { useStore } from "../store/store";

export function KillSwitch() {
  const kill = useStore((s) => s.kill);
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-danger">Halt all agent action now?</span>
        <button
          className="rounded bg-danger px-3 py-1 text-xs font-bold uppercase text-void"
          onClick={() => {
            kill("operator pressed kill switch");
            setConfirming(false);
          }}
        >
          Confirm halt
        </button>
        <button
          className="rounded border border-hud-dim px-3 py-1 text-xs uppercase text-hud-dim"
          onClick={() => setConfirming(false)}
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <button
      className="rounded border-2 border-danger px-4 py-1 text-xs font-bold uppercase tracking-wider text-danger hover:bg-danger hover:text-void"
      onClick={() => setConfirming(true)}
    >
      Kill switch
    </button>
  );
}
```

- [ ] **Step 4: Write `desktop-ui/src/components/StatusPanel.tsx`**

```tsx
import { useEffect } from "react";
import { useStore } from "../store/store";

export function StatusPanel() {
  const { status, statusError, refreshStatus, phase } = useStore();

  useEffect(() => {
    if (phase !== "ready") return;
    void refreshStatus();
    const t = setInterval(() => void refreshStatus(), 5000);
    return () => clearInterval(t);
  }, [phase, refreshStatus]);

  return (
    <aside className="w-64 space-y-2 border-l border-hud-dim/30 bg-panel/50 p-4 text-xs">
      <h2 className="text-[10px] uppercase tracking-[0.3em] text-hud-dim">Status</h2>
      {statusError && <p className="text-danger">{statusError}</p>}
      {status ? (
        <dl className="space-y-1 text-hud-dim">
          <Row k="uptime" v={`${status.uptime_seconds.toFixed(0)}s`} />
          <Row k="version" v={status.server_version} />
          <Row k="scopes" v={status.active_scopes.join(", ") || "—"} />
          <Row k="busy" v={status.busy ? "yes" : "no"} />
        </dl>
      ) : (
        <p className="text-hud-dim">No reading yet.</p>
      )}
    </aside>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between">
      <dt>{k}</dt>
      <dd className="text-hud">{v}</dd>
    </div>
  );
}
```

- [ ] **Step 5: Update `desktop-ui/src/App.tsx` to mount the panel and kill switch**

```tsx
import { ConnectionBar } from "./components/ConnectionBar";
import { EventStream } from "./components/EventStream";
import { CommandInput } from "./components/CommandInput";
import { StatusPanel } from "./components/StatusPanel";
import { KillSwitch } from "./components/KillSwitch";

export default function App() {
  return (
    <div className="flex h-screen flex-col bg-void text-hud">
      <ConnectionBar />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-h-0 flex-1 flex-col">
          <EventStream />
          <CommandInput />
        </div>
        <StatusPanel />
      </div>
      <div className="flex items-center justify-end border-t border-hud-dim/30 bg-panel/80 px-4 py-2">
        <KillSwitch />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run the test and typecheck**

Run: `pnpm exec vitest run src/components/KillSwitch.test.tsx && pnpm typecheck`
Expected: PASS (1 test); `tsc --noEmit` exits 0.

- [ ] **Step 7: Commit**

```bash
git add desktop-ui/src/App.tsx desktop-ui/src/components/StatusPanel.tsx desktop-ui/src/components/KillSwitch.tsx desktop-ui/src/components/KillSwitch.test.tsx
git commit -m "feat(desktop-ui): status panel polling + kill switch with confirm"
```

---

## Task 10: WireInspector

**Files:**
- Create: `desktop-ui/src/components/WireInspector.tsx`, `desktop-ui/src/components/WireInspector.test.tsx`
- Modify: `desktop-ui/src/App.tsx`

**Interfaces:**
- Consumes: `useStore` (`wire`).
- Produces: a collapsible raw in/out JSON log with per-message validation pass/fail.

- [ ] **Step 1: Write the failing test `desktop-ui/src/components/WireInspector.test.tsx`**

```tsx
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WireInspector } from "./WireInspector";
import { useStore } from "../store/store";

describe("WireInspector", () => {
  beforeEach(() =>
    useStore.setState({
      wire: [
        { entryId: "w1", direction: "in", type: "server.hello", raw: { type: "server.hello" }, valid: true, at: "t" },
        { entryId: "w2", direction: "out", type: "command.submit", raw: { type: "command.submit" }, valid: true, at: "t" },
      ],
    }),
  );

  it("toggles open to reveal wire entries", async () => {
    render(<WireInspector />);
    expect(screen.queryByText(/server\.hello/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /wire/i }));
    expect(screen.getByText(/server\.hello/)).toBeInTheDocument();
    expect(screen.getByText(/command\.submit/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run src/components/WireInspector.test.tsx`
Expected: FAIL — cannot find module `./WireInspector`.

- [ ] **Step 3: Write `desktop-ui/src/components/WireInspector.tsx`**

```tsx
import { useState } from "react";
import { useStore } from "../store/store";

export function WireInspector() {
  const wire = useStore((s) => s.wire);
  const [open, setOpen] = useState(false);

  return (
    <section className="border-t border-hud-dim/30 bg-void/80">
      <button
        className="flex w-full items-center gap-2 px-4 py-1 text-[10px] uppercase tracking-[0.3em] text-hud-dim"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "▼" : "▶"} Wire · {wire.length}
      </button>
      {open && (
        <div className="max-h-48 overflow-y-auto px-4 pb-2 font-mono text-[11px]">
          {wire.map((e) => (
            <div key={e.entryId} className="flex gap-2 border-b border-hud-dim/10 py-0.5">
              <span className={e.direction === "in" ? "text-hud" : "text-amber"}>
                {e.direction === "in" ? "◀" : "▶"}
              </span>
              <span className={e.valid ? "text-safe" : "text-danger"}>
                {e.valid ? "✓" : "✗"}
              </span>
              <span className="text-hud-dim">{e.type}</span>
              <span className="truncate text-hud-dim/60">{JSON.stringify(e.raw)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Mount it in `desktop-ui/src/App.tsx`**

Add the import and place `<WireInspector />` directly above the kill-switch footer:

```tsx
import { WireInspector } from "./components/WireInspector";
```

```tsx
      <WireInspector />
      <div className="flex items-center justify-end border-t border-hud-dim/30 bg-panel/80 px-4 py-2">
        <KillSwitch />
      </div>
```

- [ ] **Step 5: Run the test and typecheck**

Run: `pnpm exec vitest run src/components/WireInspector.test.tsx && pnpm typecheck`
Expected: PASS (1 test); `tsc --noEmit` exits 0.

- [ ] **Step 6: Commit**

```bash
git add desktop-ui/src/components/WireInspector.tsx desktop-ui/src/components/WireInspector.test.tsx desktop-ui/src/App.tsx
git commit -m "feat(desktop-ui): collapsible wire inspector with validation badges"
```

---

## Task 11: HUD styling pass

**Files:**
- Modify: `desktop-ui/src/index.css`, `desktop-ui/src/App.tsx`

**Interfaces:**
- Consumes: existing components/theme tokens.
- Produces: the holographic-HUD finish (scanline/grid texture, vignette) without changing component logic. Lean on the `frontend-design` / `impeccable` skills here.

- [ ] **Step 1: Add HUD texture utilities to `desktop-ui/src/index.css`**

Append:

```css
@layer utilities {
  .hud-grid {
    background-image:
      linear-gradient(rgba(56, 225, 255, 0.04) 1px, transparent 1px),
      linear-gradient(90deg, rgba(56, 225, 255, 0.04) 1px, transparent 1px);
    background-size: 28px 28px;
  }
  .hud-scanlines {
    background-image: repeating-linear-gradient(
      0deg,
      rgba(0, 0, 0, 0.18) 0px,
      rgba(0, 0, 0, 0.18) 1px,
      transparent 1px,
      transparent 3px
    );
  }
  .hud-vignette {
    box-shadow: inset 0 0 180px rgba(0, 0, 0, 0.85);
  }
}
```

- [ ] **Step 2: Apply the texture layers in `desktop-ui/src/App.tsx`**

Wrap the root so the grid sits behind content and the vignette/scanlines overlay on top:

```tsx
import { ConnectionBar } from "./components/ConnectionBar";
import { EventStream } from "./components/EventStream";
import { CommandInput } from "./components/CommandInput";
import { StatusPanel } from "./components/StatusPanel";
import { KillSwitch } from "./components/KillSwitch";
import { WireInspector } from "./components/WireInspector";

export default function App() {
  return (
    <div className="hud-grid relative flex h-screen flex-col bg-void text-hud">
      <div className="hud-scanlines hud-vignette pointer-events-none absolute inset-0 z-10" />
      <div className="relative z-0 flex h-full flex-col">
        <ConnectionBar />
        <div className="flex min-h-0 flex-1">
          <div className="flex min-h-0 flex-1 flex-col">
            <EventStream />
            <CommandInput />
          </div>
          <StatusPanel />
        </div>
        <WireInspector />
        <div className="flex items-center justify-end border-t border-hud-dim/30 bg-panel/80 px-4 py-2">
          <KillSwitch />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify tests still pass and typecheck is clean**

Run: `pnpm test && pnpm typecheck`
Expected: all suites PASS; `tsc --noEmit` exits 0.

- [ ] **Step 4: Manual visual check**

`pnpm dev` against the running mock; confirm the grid/scanlines/vignette read as a HUD and text stays legible.

- [ ] **Step 5: Commit**

```bash
git add desktop-ui/src/index.css desktop-ui/src/App.tsx
git commit -m "feat(desktop-ui): holographic-HUD texture pass (grid, scanlines, vignette)"
```

---

## Task 12: Tauri v2 shell

**Files:**
- Create: `desktop-ui/src-tauri/Cargo.toml`, `desktop-ui/src-tauri/build.rs`, `desktop-ui/src-tauri/tauri.conf.json`, `desktop-ui/src-tauri/capabilities/default.json`, `desktop-ui/src-tauri/src/main.rs`
- Modify: `desktop-ui/package.json` (Tauri dev deps + http plugin)

**Interfaces:**
- Consumes: the Vite renderer (Tasks 1–11), the dynamic `@tauri-apps/plugin-http` import (Task 6).
- Produces: a native desktop window running the dashboard, with `GET /status` allowed to the brain origin.

- [ ] **Step 1: Install the Rust toolchain**

Run (PowerShell):

```powershell
winget install --id Rustlang.Rustup -e --accept-source-agreements --accept-package-agreements
```

Then open a fresh shell and verify:

```bash
rustc --version && cargo --version
```

Expected: both print versions. (If `winget` is unavailable, install via https://rustup.rs and re-open the shell.)

- [ ] **Step 2: Add Tauri tooling + the HTTP plugin to `desktop-ui/`**

Run from `desktop-ui/`:

```bash
pnpm add -D @tauri-apps/cli@^2
pnpm add @tauri-apps/api@^2 @tauri-apps/plugin-http@^2
```

- [ ] **Step 3: Create `desktop-ui/src-tauri/Cargo.toml`**

```toml
[package]
name = "alfred-desktop-ui"
version = "0.1.0"
description = "ALFRED desktop dashboard"
edition = "2021"

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-http = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"

[features]
custom-protocol = ["tauri/custom-protocol"]
```

- [ ] **Step 4: Create `desktop-ui/src-tauri/build.rs`**

```rust
fn main() {
    tauri_build::build()
}
```

- [ ] **Step 5: Create `desktop-ui/src-tauri/src/main.rs`**

```rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .run(tauri::generate_context!())
        .expect("error while running ALFRED desktop UI");
}
```

- [ ] **Step 6: Create `desktop-ui/src-tauri/tauri.conf.json`**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "ALFRED",
  "version": "0.1.0",
  "identifier": "local.alfred.desktop",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:1420",
    "beforeDevCommand": "pnpm dev",
    "beforeBuildCommand": "pnpm build"
  },
  "app": {
    "windows": [
      {
        "title": "ALFRED",
        "width": 1100,
        "height": 720,
        "resizable": true,
        "theme": "Dark"
      }
    ],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' ws://127.0.0.1:8765 http://127.0.0.1:8765 ipc: http://ipc.localhost"
    }
  }
}
```

- [ ] **Step 7: Create `desktop-ui/src-tauri/capabilities/default.json`**

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default capabilities for the ALFRED dashboard.",
  "windows": ["main"],
  "permissions": [
    "core:default",
    {
      "identifier": "http:default",
      "allow": [{ "url": "http://127.0.0.1:8765/*" }]
    }
  ]
}
```

- [ ] **Step 8: Run the Tauri dev window against the mock brain**

In `protocol/`: `uv run uvicorn mock.server:app --port 8765`.
In `desktop-ui/`: `pnpm tauri dev`.
Expected: the first run compiles the Rust shell (slow), then a native ALFRED window opens. Click **Connect**, send "check the build", and confirm the stream renders and the **Status** panel populates (this exercises the Tauri HTTP plugin path, proving CORS is bypassed).

- [ ] **Step 9: Commit**

```bash
git add desktop-ui/src-tauri desktop-ui/package.json desktop-ui/pnpm-lock.yaml
git commit -m "feat(desktop-ui): Tauri v2 shell with HTTP plugin for status"
```

---

## Task 13: Integration test + docs + full green

**Files:**
- Create: `desktop-ui/src/protocol/integration.test.ts`, `desktop-ui/README.md`, `desktop-ui/.gitignore`
- Modify: `AGENTS.md` (monorepo table: desktop-ui status)

**Interfaces:**
- Consumes: `ProtocolClient` (Tasks 3–4) against the live mock brain.
- Produces: an end-to-end contract check (opt-in via env), documentation, and a clean full suite.

- [ ] **Step 1: Create `desktop-ui/.gitignore`**

```gitignore
node_modules
dist
src-tauri/target
src-tauri/gen
```

- [ ] **Step 2: Write the integration test `desktop-ui/src/protocol/integration.test.ts`**

```ts
// @vitest-environment node
// Opt-in: requires the mock brain running.
//   protocol/$ uv run uvicorn mock.server:app --port 8765
//   desktop-ui/$ ALFRED_MOCK_WS=ws://127.0.0.1:8765/ws pnpm exec vitest run src/protocol/integration.test.ts
import { describe, it, expect } from "vitest";
import { ProtocolClient } from "./client";
import type { Message } from "@alfred/protocol";

const URL = process.env.ALFRED_MOCK_WS;

describe.skipIf(!URL)("end-to-end against the mock brain", () => {
  it("completes a full command turn with only valid messages", async () => {
    const client = new ProtocolClient({ url: URL!, reconnect: false });
    const seen: string[] = [];

    const done = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("timed out")), 5000);
      client.on("message", (m: Message) => {
        seen.push(m.type);
        if (m.type === "server.hello") client.submitCommand("check the build");
        if (m.type === "agent.turn_complete") {
          clearTimeout(timer);
          resolve();
        }
        if (m.type === "error") {
          clearTimeout(timer);
          reject(new Error(`server error: ${m.message}`));
        }
      });
      client.on("phase", (e) => {
        if (e.phase === "error") {
          clearTimeout(timer);
          reject(new Error(e.error ?? "connection error"));
        }
      });
      client.connect();
    });

    await done;
    client.disconnect();
    expect(seen).toContain("server.hello");
    expect(seen).toContain("agent.turn_complete");
  });
});
```

- [ ] **Step 3: Run the integration test against the live mock**

In `protocol/`: `uv run uvicorn mock.server:app --port 8765`.
In `desktop-ui/`:

```bash
ALFRED_MOCK_WS=ws://127.0.0.1:8765/ws pnpm exec vitest run src/protocol/integration.test.ts
```

Expected: PASS (1 test). Without the env var, the suite reports the test as skipped.

- [ ] **Step 4: Write `desktop-ui/README.md`**

```markdown
# ALFRED Desktop UI

The JARVIS dashboard — a Tauri + React client of the ALFRED brain over the frozen
`protocol/` contract. Renders the live event stream, sends commands, shows status,
and exposes a kill switch. Voice and the memory panel are deferred.

## Develop

```bash
# 1. Start the mock brain (from ../protocol)
uv run uvicorn mock.server:app --port 8765

# 2. Run the dashboard (from desktop-ui)
pnpm install
pnpm dev            # browser renderer at http://localhost:1420 (/status proxied to the mock)
pnpm tauri dev      # native window (requires the Rust toolchain)
```

Point at the real brain later by changing the URL in the connection bar — same contract.

## Test

```bash
pnpm test           # unit + component suites
pnpm typecheck      # tsc --noEmit, strict
# end-to-end against a running mock brain:
ALFRED_MOCK_WS=ws://127.0.0.1:8765/ws pnpm exec vitest run src/protocol/integration.test.ts
```

## Contract

Types come from `@alfred/protocol` and the schema from `@alfred/protocol-schema`
(aliases into the frozen `../protocol/`). Never redefine a message shape; a needed
new message is a coordinated `protocol/` change, not a local invention.
```

- [ ] **Step 5: Update the monorepo table in `AGENTS.md`**

Change the `desktop-ui/` row from:

```
| `desktop-ui/` | TypeScript (Tauri/React) | Phase 4 (dashboard + voice) — not yet started |
```

to:

```
| `desktop-ui/` | TypeScript (Tauri/React) | Phase 4 — dashboard MVP built (event stream, command, status, kill switch, wire inspector); voice + memory panel deferred |
```

- [ ] **Step 6: Run the full suite and typecheck**

Run: `pnpm test && pnpm typecheck`
Expected: every suite PASS (integration test skipped without the env var); `tsc --noEmit` exits 0.

- [ ] **Step 7: Commit**

```bash
git add desktop-ui/src/protocol/integration.test.ts desktop-ui/README.md desktop-ui/.gitignore AGENTS.md
git commit -m "test(desktop-ui): e2e against mock brain + docs and status update"
```

---

## Self-Review notes

- **Spec coverage:** §1 six surfaces → Tasks 8 (stream/command/connection), 9 (status/kill), 10 (wire). §2 layers → Tasks 2–7. §3 contract/aliases/CORS → Tasks 1, 6, 12. §4 HUD → Tasks 8–11. §5 testing → every task is TDD; integration in Task 13. §6 sequencing → task order; Rust installed in Task 12 per the approved "install now, shell last" sequencing. §7 risks → CORS (Task 6/12), alias sourcing (Task 1), rustup (Task 12).
- **Type consistency:** `ProtocolClient` event names (`phase`/`message`/`wire`), `WireEntry.entryId`, `Turn`/`TurnAction` fields, and store action names (`submit`/`kill`/`refreshStatus`) are used identically across producing and consuming tasks.
- **Contract fidelity:** every emitted message is built with the envelope and validated before send; optional fields (`scope_override`, `reason`) are spread-in only when present, never `null`.

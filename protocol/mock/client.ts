/**
 * Reference mock "fake UI" client.
 *
 * Connects to a mock brain, performs the protocol handshake, submits one
 * command, and validates every received message against the schema with Ajv.
 * Exits 0 if the full turn completes with only valid messages; exits 1 on the
 * first invalid message or on timeout.
 *
 *   pnpm exec tsx mock/client.ts --url ws://127.0.0.1:8765/ws
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import WebSocket from "ws";
import { Ajv2020 } from "ajv/dist/2020.js";
import * as addFormatsModule from "ajv-formats";
const addFormats = addFormatsModule.default as unknown as (ajv: InstanceType<typeof Ajv2020>) => void;
import type { Message } from "../gen/typescript/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(
  readFileSync(join(here, "..", "schema", "protocol.schema.json"), "utf-8"),
);
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

function urlArg(): string {
  const i = process.argv.indexOf("--url");
  return i >= 0 ? process.argv[i + 1] : "ws://127.0.0.1:8765/ws";
}

function envelope() {
  return { v: 1 as const, id: `ui-${Math.floor(performance.now())}`, ts: new Date().toISOString() };
}

function fail(reason: string): never {
  console.error(`✗ ${reason}`);
  process.exit(1);
}

const ws = new WebSocket(urlArg());
const timer = setTimeout(() => fail("timed out waiting for turn_complete"), 5000);

ws.on("open", () => {
  const hello: Message = {
    ...envelope(), type: "client.hello",
    client_name: "mock-ui", client_version: "0.1.0", protocol_version: 1,
  };
  ws.send(JSON.stringify(hello));
});

let sawServerHello = false;

ws.on("message", (raw) => {
  const data = JSON.parse(raw.toString()) as Record<string, unknown>;
  if (!validate(data)) {
    fail(`invalid message ${data?.["type"]}: ${ajv.errorsText(validate.errors)}`);
  }
  console.log(`✓ ${data["type"]}`);

  if (data["type"] === "server.hello") {
    sawServerHello = true;
    const cmd: Message = {
      ...envelope(), type: "command.submit",
      text: "check the build", channel: "desktop",
    };
    ws.send(JSON.stringify(cmd));
  } else if (data["type"] === "agent.turn_complete") {
    clearTimeout(timer);
    if (!sawServerHello) fail("turn completed without a server.hello");
    console.log("✓ turn complete — contract verified end-to-end");
    ws.close();
    process.exit(0);
  } else if (data["type"] === "error") {
    fail(`server error: ${String(data["code"])} ${String(data["message"])}`);
  }
});

ws.on("error", (err) => fail(`socket error: ${err.message}`));

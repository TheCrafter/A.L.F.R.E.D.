// Compile-time only: proves the generated types are usable and coherent.
// Checked by `tsc --noEmit`; never executed.
import type {
  Message,
  CommandSubmit,
  ServerHello,
  AgentMessage,
  Error as ProtocolError,
  StatusResponse,
} from "../../gen/typescript/index.js";

const command: CommandSubmit = {
  v: 1,
  id: "x",
  ts: "2026-06-23T10:00:02Z",
  type: "command.submit",
  text: "check the build",
  channel: "desktop",
};

const hello: ServerHello = {
  v: 1,
  id: "y",
  ts: "2026-06-23T10:00:00Z",
  type: "server.hello",
  corr: "x",
  server_name: "alfred-brain",
  server_version: "0.1.0",
  protocol_version: 1,
  session_id: "sess-abc",
};

const chunk: AgentMessage = {
  v: 1, id: "z", ts: "2026-06-23T10:00:05Z",
  type: "agent.message", corr: "x", text: "…", final: true,
};

const err: ProtocolError = {
  v: 1, id: "e", ts: "2026-06-23T10:00:08Z",
  type: "error", code: "unknown_type", message: "nope",
};

const status: StatusResponse = {
  v: 1,
  id: "s",
  ts: "2026-06-23T10:00:01Z",
  type: "status.response",
  corr: "x",
  uptime_seconds: 42,
  server_version: "0.1.0",
  active_scopes: ["business"],
  busy: false,
};

// All five must be assignable to the discriminated union.
const all: Message[] = [command, hello, chunk, err, status];
void all;

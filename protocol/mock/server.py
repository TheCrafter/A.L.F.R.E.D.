"""Reference mock 'fake brain'.

A scripted replayer with ZERO reasoning. It exists only so the desktop-ui can
develop against a live, contract-valid endpoint while the real brain is built
in a separate session. It builds every outgoing message from the generated
Pydantic models, so anything it emits is guaranteed to satisfy the contract.

Run it:
    uv run uvicorn mock.server:app --port 8765
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from alfred_protocol import (
    AgentAction,
    AgentMessage,
    AgentThought,
    AgentTurnComplete,
    CommandAck,
    Error,
    KillSwitchAck,
    ServerHello,
    StatusResponse,
)

SUPPORTED_PROTOCOL_VERSION = 1
SERVER_NAME = "alfred-mock-brain"
SERVER_VERSION = "0.1.0"

app = FastAPI(title="ALFRED mock brain")
_ids = itertools.count(1)
_started = datetime.now(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mid() -> str:
    return f"mock-{next(_ids)}"


def _dump(model) -> dict:
    # mode="json" so datetimes/enums serialize to JSON-native values.
    # exclude_none=True drops optional fields that are None (schema doesn't allow null).
    return model.model_dump(mode="json", exclude_none=True)


@app.get("/status")
def status() -> dict:
    uptime = (datetime.now(timezone.utc) - _started).total_seconds()
    return _dump(StatusResponse(
        v=1, id=_mid(), ts=_now(), type="status.response",
        corr="http-status", uptime_seconds=uptime,
        server_version=SERVER_VERSION, active_scopes=["coding"], busy=False,
    ))


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    try:
        hello = await socket.receive_json()
        if hello.get("type") != "client.hello":
            await socket.send_json(_dump(Error(
                v=1, id=_mid(), ts=_now(), type="error",
                code="bad_message", message="Expected client.hello first.",
            )))
            await socket.close()
            return
        if hello.get("protocol_version") != SUPPORTED_PROTOCOL_VERSION:
            await socket.send_json(_dump(Error(
                v=1, id=_mid(), ts=_now(), type="error", corr=hello.get("id"),
                code="unsupported_version",
                message=f"This server speaks protocol v{SUPPORTED_PROTOCOL_VERSION}.",
            )))
            await socket.close()
            return

        await socket.send_json(_dump(ServerHello(
            v=1, id=_mid(), ts=_now(), type="server.hello", corr=hello["id"],
            server_name=SERVER_NAME, server_version=SERVER_VERSION,
            protocol_version=SUPPORTED_PROTOCOL_VERSION, session_id="mock-session",
        )))

        while True:
            msg = await socket.receive_json()
            kind = msg.get("type")
            if kind == "command.submit":
                await _run_command_turn(socket, msg["id"])
            elif kind == "kill_switch.activate":
                await socket.send_json(_dump(KillSwitchAck(
                    v=1, id=_mid(), ts=_now(), type="kill_switch.ack",
                    corr=msg["id"], halted=True,
                )))
            else:
                await socket.send_json(_dump(Error(
                    v=1, id=_mid(), ts=_now(), type="error", corr=msg.get("id"),
                    code="unknown_type", message=f"Unhandled type: {kind}",
                )))
    except WebSocketDisconnect:
        return


async def _run_command_turn(socket: WebSocket, corr: str) -> None:
    await socket.send_json(_dump(CommandAck(
        v=1, id=_mid(), ts=_now(), type="command.ack", corr=corr, accepted=True,
    )))
    await socket.send_json(_dump(AgentThought(
        v=1, id=_mid(), ts=_now(), type="agent.thought", corr=corr,
        text="Inspecting the project for a build script.",
    )))
    await socket.send_json(_dump(AgentAction(
        v=1, id=_mid(), ts=_now(), type="agent.action", corr=corr,
        tool="shell", summary="Run `npm run build`", risk="sensitive",
    )))
    await socket.send_json(_dump(AgentMessage(
        v=1, id=_mid(), ts=_now(), type="agent.message", corr=corr,
        text="The build is ", final=False,
    )))
    await socket.send_json(_dump(AgentMessage(
        v=1, id=_mid(), ts=_now(), type="agent.message", corr=corr,
        text="green, sir.", final=True,
    )))
    await socket.send_json(_dump(AgentTurnComplete(
        v=1, id=_mid(), ts=_now(), type="agent.turn_complete", corr=corr,
        status="completed",
    )))

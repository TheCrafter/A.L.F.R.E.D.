from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from alfred_protocol import (
    CommandAck, Error, KillSwitchAck, ServerHello, StatusResponse,
)

from . import SERVER_NAME, SERVER_VERSION
from .agent import AgentLoop
from .config import Settings, effective_config
from .events import EventBus
from .messages import dump, new_id, now_ts
from .persona import system_prompt
from .providers.base import ReasoningProvider
from .providers.registry import available_models, build_explicit, build_provider
from .session import TurnManager
from .tools.echo import EchoTool
from .tools.registry import ToolRegistry

SUPPORTED_PROTOCOL_VERSION = 1


class ModelSelect(BaseModel):
    provider: str
    model: str


def create_app(settings: Settings, provider: ReasoningProvider | None = None) -> FastAPI:
    bus = EventBus()
    registry = ToolRegistry()
    registry.register(EchoTool())
    provider = provider or build_provider(settings)
    agent = AgentLoop(provider, registry, system_prompt(settings.persona_intensity),
                      settings.max_tool_iterations)
    turns = TurnManager()
    started = datetime.now(timezone.utc)

    app = FastAPI(title="ALFRED brain")
    app.state.turns = turns
    app.state.agent = agent

    state = {"settings": settings}

    def _model_for(p: ReasoningProvider) -> str:
        if p.name == "gemini":
            return settings.gemini_model
        if p.name == "groq":
            return settings.groq_model
        return "scripted"

    # Mutable record of the live provider+model, swappable at runtime via /models.
    current = {"provider": provider.name, "model": _model_for(provider)}

    @app.get("/config")
    def get_config() -> dict:
        return {"config": effective_config(state["settings"])}

    @app.get("/models")
    def models() -> dict:
        return {"current": current, "available": available_models(settings)}

    @app.post("/models")
    def set_model(sel: ModelSelect) -> dict:
        try:
            new_provider = build_explicit(settings, sel.provider, sel.model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        agent.set_provider(new_provider)
        current["provider"] = new_provider.name
        current["model"] = "scripted" if new_provider.name == "scripted" else sel.model
        return {"current": current, "available": available_models(settings)}

    def _status(corr: str) -> dict:
        uptime = (datetime.now(timezone.utc) - started).total_seconds()
        return dump(StatusResponse(
            v=1, id=new_id(), ts=now_ts(), type="status.response", corr=corr,
            uptime_seconds=uptime, server_version=SERVER_VERSION,
            active_scopes=[], busy=turns.active_count > 0,
        ))

    @app.get("/status")
    def status() -> dict:
        return _status("http-status")

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        # --- handshake (direct sends; no bus subscription yet) ---
        try:
            hello = await socket.receive_json()
        except WebSocketDisconnect:
            return
        except (json.JSONDecodeError, KeyError):
            await socket.send_json(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error",
                code="bad_message", message="Expected a JSON message.")))
            await socket.close()
            return
        if hello.get("type") != "client.hello":
            await socket.send_json(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error",
                code="bad_message", message="Expected client.hello first.")))
            await socket.close()
            return
        if hello.get("protocol_version") != SUPPORTED_PROTOCOL_VERSION:
            await socket.send_json(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error", corr=hello.get("id"),
                code="unsupported_version",
                message=f"This server speaks protocol v{SUPPORTED_PROTOCOL_VERSION}.")))
            await socket.close()
            return
        hello_id = hello.get("id")
        if hello_id is None:
            await socket.send_json(dump(Error(
                v=1, id=new_id(), ts=now_ts(), type="error",
                code="bad_message", message="Message missing required 'id'.")))
            await socket.close()
            return
        await socket.send_json(dump(ServerHello(
            v=1, id=new_id(), ts=now_ts(), type="server.hello", corr=hello_id,
            server_name=SERVER_NAME, server_version=SERVER_VERSION,
            protocol_version=SUPPORTED_PROTOCOL_VERSION, session_id=f"sess-{uuid.uuid4()}")))

        # --- subscribe + single sender task serializes all further output ---
        q = bus.subscribe()

        async def sender() -> None:
            while True:
                msg = await q.get()
                await socket.send_json(msg)

        sender_task = asyncio.create_task(sender())
        my_turns: list[asyncio.Task] = []
        try:
            while True:
                try:
                    msg = await socket.receive_json()
                except (json.JSONDecodeError, KeyError):
                    q.put_nowait(dump(Error(
                        v=1, id=new_id(), ts=now_ts(), type="error",
                        code="bad_message", message="Expected a JSON message.")))
                    continue
                kind = msg.get("type")
                mid = msg.get("id")
                if mid is None:
                    q.put_nowait(dump(Error(
                        v=1, id=new_id(), ts=now_ts(), type="error",
                        code="bad_message", message="Message missing required 'id'.")))
                    continue
                if kind == "command.submit":
                    bus.publish(dump(CommandAck(
                        v=1, id=new_id(), ts=now_ts(), type="command.ack",
                        corr=mid, accepted=True)))
                    my_turns.append(turns.start(mid, agent.run(
                        corr=mid, text=msg.get("text", ""), publish=bus.publish)))
                elif kind == "kill_switch.activate":
                    await turns.kill_all()
                    q.put_nowait(dump(KillSwitchAck(
                        v=1, id=new_id(), ts=now_ts(), type="kill_switch.ack",
                        corr=mid, halted=True)))
                elif kind == "status.request":
                    q.put_nowait(_status(mid))
                else:
                    q.put_nowait(dump(Error(
                        v=1, id=new_id(), ts=now_ts(), type="error", corr=mid,
                        code="unknown_type", message=f"Unhandled type: {kind}")))
        except WebSocketDisconnect:
            pass
        finally:
            # Cancel this connection's in-flight turns so they don't keep
            # running (and leaking output to the bus) after the client is gone.
            for t in my_turns:
                if not t.done():
                    t.cancel()
            bus.unsubscribe(q)
            sender_task.cancel()

    return app

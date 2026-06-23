from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from alfred_protocol import (
    CommandAck, Error, KillSwitchAck, ServerHello, StatusResponse,
    MemoryItem, MemoryListResponse, MemoryAck, MemoryFormed, MemoryRemoved,
)

from . import SERVER_NAME, SERVER_VERSION
from .agent import AgentLoop
from .config import Settings, effective_config, home
from .events import EventBus
from .memory import Memory, VaultMemory
from .memory.extraction import Extractor
from .memory.index import FastEmbedEmbedder
from .memory.tools import ForgetTool, RecallTool, RememberTool
from .memory.working import WorkingMemory
from .messages import dump, new_id, now_ts
from .persona import system_prompt
from .providers.base import ReasoningProvider
from .providers.registry import available_models, build_explicit, build_provider
from .session import TurnManager
from .tools.echo import EchoTool
from .tools.registry import ToolRegistry

SUPPORTED_PROTOCOL_VERSION = 1


def memory_item(rec) -> MemoryItem:
    status = rec.status if rec.status in ("provisional", "confirmed") else "confirmed"
    return MemoryItem(
        id=rec.id, text=rec.text, title=rec.title, type=rec.type,
        tags=list(rec.tags), status=status, created=rec.created,
        updated=rec.updated, links=list(rec.links),
    )


class ModelSelect(BaseModel):
    provider: str
    model: str


def create_app(settings: Settings, provider: ReasoningProvider | None = None,
               memory: "Memory | None" = None) -> FastAPI:
    bus = EventBus()
    registry = ToolRegistry()
    registry.register(EchoTool())
    provider = provider or build_provider(settings)
    if memory is None:
        vault_dir = settings.memory_vault_dir or str(home() / "vault")
        memory = VaultMemory(vault_dir, FastEmbedEmbedder(settings.memory_embed_model))
    registry.register(RememberTool(memory))
    registry.register(RecallTool(memory))
    registry.register(ForgetTool(memory))

    def _extraction_provider(s: Settings, active: ReasoningProvider) -> ReasoningProvider:
        if not s.memory_extract_model:
            return active
        try:
            return build_explicit(s, s.provider, s.memory_extract_model)
        except ValueError:
            logging.getLogger("alfred_brain").warning(
                "extract_model set but provider unavailable; using active provider")
            return active

    working = WorkingMemory(window=settings.memory_window_messages)
    extractor = Extractor(_extraction_provider(settings, provider), memory,
                          recall_k=settings.memory_extract_recall_k)
    agent = AgentLoop(provider, registry, system_prompt(settings.persona_intensity),
                      settings.max_tool_iterations,
                      memory=memory, recall_top_k=settings.memory_recall_top_k,
                      working=working, extractor=extractor)
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

    HOT_PROVIDER_FIELDS = ("provider", "groq_model", "gemini_model",
                           "groq_api_key", "gemini_api_key")
    STARTUP_ONLY = ("host", "port")

    def _apply_hot(old: Settings, new: Settings) -> tuple[list[str], list[str]]:
        changed: list[str] = []
        if any(getattr(old, f) != getattr(new, f) for f in HOT_PROVIDER_FIELDS):
            new_provider = build_provider(new)
            agent.set_provider(new_provider)
            if not new.memory_extract_model:
                extractor.set_provider(new_provider)
            current["provider"] = new_provider.name
            # Derive the model from the RELOADED settings (not _model_for, which
            # reads the captured startup `settings`).
            current["model"] = (
                "scripted" if new_provider.name == "scripted"
                else new.groq_model if new_provider.name == "groq"
                else new.gemini_model
            )
            changed.append("provider")
        if old.persona_intensity != new.persona_intensity:
            agent.set_system(system_prompt(new.persona_intensity))
            changed.append("persona_intensity")
        if old.max_tool_iterations != new.max_tool_iterations:
            agent.set_max_iterations(new.max_tool_iterations)
            changed.append("max_tool_iterations")
        if old.memory_recall_top_k != new.memory_recall_top_k:
            agent.set_recall_top_k(new.memory_recall_top_k)
            changed.append("memory_recall_top_k")
        if old.memory_window_messages != new.memory_window_messages:
            working.set_window(new.memory_window_messages)
            changed.append("memory_window_messages")
        if old.memory_extract_recall_k != new.memory_extract_recall_k:
            extractor.set_recall_k(new.memory_extract_recall_k)
            changed.append("memory_extract_recall_k")
        if old.log_level != new.log_level:
            logging.getLogger("alfred_brain").setLevel(new.log_level)
            changed.append("log_level")
        pending = [f for f in STARTUP_ONLY if getattr(old, f) != getattr(new, f)]
        return changed, pending

    @app.post("/config/reload")
    def reload_config() -> dict:
        try:
            new = Settings(_env_file=None)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        changed, pending = _apply_hot(state["settings"], new)
        state["settings"] = new
        return {"changed": changed, "startup_only_pending": pending,
                "config": effective_config(new)}

    @app.get("/models")
    def models() -> dict:
        return {"current": current, "available": available_models(state["settings"])}

    @app.post("/models")
    def set_model(sel: ModelSelect) -> dict:
        try:
            new_provider = build_explicit(state["settings"], sel.provider, sel.model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        agent.set_provider(new_provider)
        if not state["settings"].memory_extract_model:
            extractor.set_provider(new_provider)
        current["provider"] = new_provider.name
        current["model"] = "scripted" if new_provider.name == "scripted" else sel.model
        return {"current": current, "available": available_models(state["settings"])}

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
                elif kind == "memory.list_request":
                    want = msg.get("status")
                    recs = sorted(memory.all(), key=lambda r: r.created, reverse=True)
                    items = [memory_item(r) for r in recs
                             if want is None or r.status == want]
                    q.put_nowait(dump(MemoryListResponse(
                        v=1, id=new_id(), ts=now_ts(), type="memory.list_response",
                        corr=mid, items=items)))
                elif kind == "memory.edit":
                    rec = memory.update(
                        msg.get("mem_id", ""),
                        status=msg.get("status"), tags=msg.get("tags"))
                    if rec is None:
                        q.put_nowait(dump(MemoryAck(
                            v=1, id=new_id(), ts=now_ts(), type="memory.ack",
                            corr=mid, ok=False, error="memory not found")))
                    else:
                        q.put_nowait(dump(MemoryAck(
                            v=1, id=new_id(), ts=now_ts(), type="memory.ack",
                            corr=mid, ok=True)))
                        bus.publish(dump(MemoryFormed(
                            v=1, id=new_id(), ts=now_ts(), type="memory.formed",
                            item=memory_item(rec), op="update")))
                elif kind == "memory.delete":
                    ok = memory.forget(msg.get("mem_id", ""))
                    q.put_nowait(dump(MemoryAck(
                        v=1, id=new_id(), ts=now_ts(), type="memory.ack",
                        corr=mid, ok=ok, **({} if ok else {"error": "memory not found"}))))
                    if ok:
                        bus.publish(dump(MemoryRemoved(
                            v=1, id=new_id(), ts=now_ts(), type="memory.removed",
                            mem_id=msg.get("mem_id", ""))))
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

    @app.on_event("shutdown")
    async def _flush_memory() -> None:
        await agent.drain_extractions()
        await extractor.extract(working.drain())

    return app

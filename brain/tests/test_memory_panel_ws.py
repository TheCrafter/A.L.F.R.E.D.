"""WS handler tests for memory.list_request / memory.edit / memory.delete."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.memory import VaultMemory
from alfred_brain.server import create_app
from tests.test_memory_index import FakeEmbedder

ENV = {"v": 1, "id": "ui-1", "ts": "2026-06-23T10:00:00Z"}


def _settings() -> Settings:
    return Settings(provider="scripted", _env_file=None)


def _make_memory(tmp_path):
    """Return a VaultMemory seeded with two records (provisional + confirmed)."""
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    # Insert provisional first (older), confirmed second (newer).
    # We control ordering by inserting in sequence; vault timestamps are second-granular
    # so we rely on insertion order yielding distinct created values.
    mem.remember("provisional note alpha", status="provisional", tags=["tag-p"])
    # Sleep 1.1 s so the two records get distinct created timestamps.
    time.sleep(1.1)
    mem.remember("confirmed note beta", status="confirmed", tags=["tag-c"])
    return mem


def _handshake(ws) -> None:
    ws.send_json({**ENV, "type": "client.hello",
                  "client_name": "t", "client_version": "0", "protocol_version": 1})
    hello = ws.receive_json()
    assert hello["type"] == "server.hello"


# ---------------------------------------------------------------------------
# 1. list_request returns all items, newest-first
# ---------------------------------------------------------------------------
def test_list_request_returns_items(tmp_path):
    mem = _make_memory(tmp_path)
    app = create_app(_settings(), memory=mem)
    with TestClient(app).websocket_connect("/ws") as ws:
        _handshake(ws)
        ws.send_json({**ENV, "id": "lr-1", "type": "memory.list_request"})
        resp = ws.receive_json()
    assert resp["type"] == "memory.list_response"
    assert resp["corr"] == "lr-1"
    items = resp["items"]
    assert len(items) == 2
    # newest-first: confirmed (inserted second) should come before provisional
    assert items[0]["status"] == "confirmed"
    assert items[1]["status"] == "provisional"


# ---------------------------------------------------------------------------
# 2. list_request with status filter returns only matching items
# ---------------------------------------------------------------------------
def test_list_request_status_filter(tmp_path):
    mem = _make_memory(tmp_path)
    app = create_app(_settings(), memory=mem)
    with TestClient(app).websocket_connect("/ws") as ws:
        _handshake(ws)
        ws.send_json({**ENV, "id": "lr-2", "type": "memory.list_request",
                      "status": "provisional"})
        resp = ws.receive_json()
    assert resp["type"] == "memory.list_response"
    assert len(resp["items"]) == 1
    assert resp["items"][0]["status"] == "provisional"


# ---------------------------------------------------------------------------
# 3. memory.edit confirms a record → memory.ack{ok:true} + memory.formed{op:update}
# ---------------------------------------------------------------------------
def test_edit_confirms_and_acks_and_broadcasts(tmp_path):
    mem = _make_memory(tmp_path)
    # get the id of the provisional record
    prov = next(r for r in mem.all() if r.status == "provisional")
    app = create_app(_settings(), memory=mem)
    with TestClient(app).websocket_connect("/ws") as ws:
        _handshake(ws)
        ws.send_json({**ENV, "id": "ed-1", "type": "memory.edit",
                      "mem_id": prov.id, "status": "confirmed"})
        # expect ack first, then formed broadcast (both via the queue)
        ack = ws.receive_json()
        formed = ws.receive_json()
    assert ack["type"] == "memory.ack"
    assert ack["corr"] == "ed-1"
    assert ack["ok"] is True
    assert formed["type"] == "memory.formed"
    assert formed["op"] == "update"
    assert formed["item"]["status"] == "confirmed"
    assert formed["item"]["id"] == prov.id


# ---------------------------------------------------------------------------
# 4. memory.edit with unknown id → memory.ack{ok:false}; no memory.formed
# ---------------------------------------------------------------------------
def test_edit_unknown_id_nacks(tmp_path):
    mem = _make_memory(tmp_path)
    app = create_app(_settings(), memory=mem)
    with TestClient(app).websocket_connect("/ws") as ws:
        _handshake(ws)
        ws.send_json({**ENV, "id": "ed-2", "type": "memory.edit",
                      "mem_id": "no-such-id", "status": "confirmed"})
        ack = ws.receive_json()
        # issue a status.request to flush any pending messages; if another
        # message arrives before status.response it means we got an unexpected broadcast
        ws.send_json({**ENV, "id": "st-x", "type": "status.request"})
        next_msg = ws.receive_json()
    assert ack["type"] == "memory.ack"
    assert ack["ok"] is False
    assert "error" in ack and ack["error"]
    # next message after the nack must be status.response, not memory.formed
    assert next_msg["type"] == "status.response"


# ---------------------------------------------------------------------------
# 5. memory.delete → memory.ack{ok:true} + memory.removed; record gone
# ---------------------------------------------------------------------------
def test_delete_forgets_acks_and_broadcasts(tmp_path):
    mem = _make_memory(tmp_path)
    conf = next(r for r in mem.all() if r.status == "confirmed")
    app = create_app(_settings(), memory=mem)
    with TestClient(app).websocket_connect("/ws") as ws:
        _handshake(ws)
        ws.send_json({**ENV, "id": "del-1", "type": "memory.delete",
                      "mem_id": conf.id})
        ack = ws.receive_json()
        removed = ws.receive_json()
    assert ack["type"] == "memory.ack"
    assert ack["corr"] == "del-1"
    assert ack["ok"] is True
    assert removed["type"] == "memory.removed"
    assert removed["mem_id"] == conf.id
    # the record must no longer appear in memory.all()
    assert not any(r.id == conf.id for r in mem.all())


# ---------------------------------------------------------------------------
# 6. memory_item() does not raise when rec.created is empty string
# ---------------------------------------------------------------------------
def test_memory_item_empty_created_does_not_raise():
    """A hand-authored vault note with no 'created' frontmatter arrives as
    rec.created == "".  memory_item() must fall back to now_ts() instead of
    blowing up with a ValidationError."""
    from dataclasses import dataclass
    from pathlib import Path

    from alfred_brain.server import memory_item

    @dataclass
    class FakeRec:
        id: str
        text: str
        title: str
        type: str
        tags: list
        status: str
        created: str
        updated: str | None
        links: list
        path: Path = Path("/fake")

    rec = FakeRec(
        id="test-id-missing-created",
        text="Hand-authored note",
        title="My Note",
        type="note",
        tags=[],
        status="confirmed",
        created="",
        updated=None,
        links=[],
    )

    result = memory_item(rec)
    assert result.created != "", "created must be filled in when rec.created is empty"

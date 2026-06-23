import asyncio
import time

from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.providers.base import Thought
from alfred_brain.server import create_app

ENV = {"v": 1, "id": "ui-1", "ts": "2026-06-23T10:00:00Z"}


def _client():
    return TestClient(create_app(Settings(provider="scripted", _env_file=None)))


def test_handshake_then_full_command_turn():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        hello = ws.receive_json()
        assert hello["type"] == "server.hello"
        assert hello["corr"] == "ui-1"

        ws.send_json({**ENV, "id": "cmd-1", "type": "command.submit",
                      "text": "check the build", "channel": "desktop"})
        seen = []
        while True:
            msg = ws.receive_json()
            seen.append(msg["type"])
            if msg["type"] == "agent.turn_complete":
                assert msg["status"] == "completed"
                break
        assert seen == [
            "command.ack", "agent.thought", "agent.action",
            "agent.message", "agent.message", "agent.turn_complete",
        ]


def test_unsupported_version_closes():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 99})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "unsupported_version"
        assert err["corr"] == "ui-1"


def test_non_hello_first_is_bad_message():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "id": "cmd-1", "type": "command.submit",
                      "text": "x", "channel": "desktop"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "bad_message"


def test_unknown_type_after_handshake():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_json({**ENV, "id": "bad-1", "type": "totally.bogus"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "unknown_type"
        assert err["corr"] == "bad-1"


def test_kill_switch_acks():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_json({**ENV, "id": "kill-1", "type": "kill_switch.activate",
                      "channel": "desktop"})
        ack = ws.receive_json()
        assert ack["type"] == "kill_switch.ack"
        assert ack["corr"] == "kill-1"
        assert ack["halted"] is True


def test_non_json_frame_after_handshake_is_bad_message_and_survives():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_text("this is not json{{{")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "bad_message"
        # the connection must stay alive: a follow-up request still works
        ws.send_json({**ENV, "id": "st-9", "type": "status.request"})
        resp = ws.receive_json()
        assert resp["type"] == "status.response"
        assert resp["corr"] == "st-9"


def test_non_json_handshake_frame_is_bad_message():
    with _client().websocket_connect("/ws") as ws:
        ws.send_text("garbage{{{")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "bad_message"


class _BlockingProvider:
    """Yields one thought, then blocks forever — keeps a turn in-flight."""
    name = "blocking"

    async def run_turn(self, messages, tools, system):
        yield Thought("thinking")
        await asyncio.Event().wait()


def test_disconnect_cancels_in_flight_turn():
    app = create_app(Settings(provider="scripted", _env_file=None), provider=_BlockingProvider())
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_json({**ENV, "id": "cmd-x", "type": "command.submit",
                      "text": "hi", "channel": "desktop"})
        ws.receive_json()  # command.ack
        ws.receive_json()  # agent.thought
        assert app.state.turns.active_count == 1
    # disconnecting must cancel the connection's in-flight turn (no orphan/leak)
    deadline = time.time() + 2
    while app.state.turns.active_count != 0 and time.time() < deadline:
        time.sleep(0.02)
    assert app.state.turns.active_count == 0


def test_status_request_over_ws():
    with _client().websocket_connect("/ws") as ws:
        ws.send_json({**ENV, "type": "client.hello",
                      "client_name": "t", "client_version": "0", "protocol_version": 1})
        ws.receive_json()  # server.hello
        ws.send_json({**ENV, "id": "st-1", "type": "status.request"})
        resp = ws.receive_json()
        assert resp["type"] == "status.response"
        assert resp["corr"] == "st-1"

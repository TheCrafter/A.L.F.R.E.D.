import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from mock.server import app, SUPPORTED_PROTOCOL_VERSION

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "protocol.schema.json"
VALIDATOR = Draft202012Validator(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8")), format_checker=FormatChecker()
)


def assert_valid(msg: dict) -> None:
    errors = sorted(VALIDATOR.iter_errors(msg), key=lambda e: e.path)
    assert not errors, "; ".join(e.message for e in errors)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def hello(version: int = SUPPORTED_PROTOCOL_VERSION) -> dict:
    return {
        "v": 1, "id": "client-hello-1", "ts": "2026-06-23T10:00:00Z",
        "type": "client.hello", "client_name": "test", "client_version": "0.0.1",
        "protocol_version": version,
    }


def test_http_status_is_valid(client: TestClient):
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()
    assert_valid(body)
    assert body["type"] == "status.response"


def test_ws_handshake_returns_server_hello(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello())
        reply = ws.receive_json()
        assert_valid(reply)
        assert reply["type"] == "server.hello"
        assert reply["corr"] == "client-hello-1"
        assert reply["protocol_version"] == SUPPORTED_PROTOCOL_VERSION


def test_command_produces_valid_event_stream(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello())
        ws.receive_json()  # server.hello
        ws.send_json({
            "v": 1, "id": "cmd-1", "ts": "2026-06-23T10:00:02Z",
            "type": "command.submit", "text": "check the build", "channel": "desktop",
        })
        seen: list[str] = []
        while True:
            msg = ws.receive_json()
            assert_valid(msg)
            assert msg.get("corr") == "cmd-1"
            seen.append(msg["type"])
            if msg["type"] == "agent.turn_complete":
                break
        assert seen[0] == "command.ack"
        assert "agent.thought" in seen
        assert "agent.action" in seen
        assert "agent.message" in seen
        assert seen[-1] == "agent.turn_complete"


def test_kill_switch_is_acknowledged(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello())
        ws.receive_json()
        ws.send_json({
            "v": 1, "id": "kill-1", "ts": "2026-06-23T10:00:07Z",
            "type": "kill_switch.activate", "channel": "telegram",
        })
        ack = ws.receive_json()
        assert_valid(ack)
        assert ack["type"] == "kill_switch.ack"
        assert ack["corr"] == "kill-1"
        assert ack["halted"] is True


def test_unsupported_version_is_rejected(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(hello(version=999))
        err = ws.receive_json()
        assert_valid(err)
        assert err["type"] == "error"
        assert err["code"] == "unsupported_version"


def test_non_hello_first_message_is_rejected(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({
            "v": 1, "id": "stray-1", "ts": "2026-06-23T10:00:00Z",
            "type": "status.request",
        })
        err = ws.receive_json()
        assert_valid(err)
        assert err["type"] == "error"
        assert err["code"] == "bad_message"

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "protocol.schema.json"
FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_is_valid_2020_12():
    schema = load_schema()
    # Raises jsonschema.exceptions.SchemaError if the schema is itself invalid.
    Draft202012Validator.check_schema(schema)


def test_schema_has_all_twenty_messages():
    schema = load_schema()
    titles = {d["title"] for d in schema["$defs"].values()}
    expected = {
        "ClientHello", "ServerHello", "StatusRequest", "StatusResponse",
        "CommandSubmit", "CommandAck", "AgentThought", "AgentAction",
        "AgentMessage", "AgentTurnComplete", "KillSwitchActivate",
        "KillSwitchAck", "Error",
        "MemoryListRequest", "MemoryListResponse", "MemoryEdit",
        "MemoryDelete", "MemoryAck", "MemoryFormed", "MemoryRemoved",
    }
    assert expected <= titles
    assert len(schema["oneOf"]) == 20


EXPECTED_TYPES = {
    "client.hello", "server.hello", "status.request", "status.response",
    "command.submit", "command.ack", "agent.thought", "agent.action",
    "agent.message", "agent.turn_complete", "kill_switch.activate",
    "kill_switch.ack", "error",
    "memory.list_request", "memory.list_response", "memory.edit",
    "memory.delete", "memory.ack", "memory.formed", "memory.removed",
}


def fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


def test_one_fixture_per_message_type():
    types = set()
    for f in fixture_files():
        types.add(json.loads(f.read_text(encoding="utf-8"))["type"])
    assert types == EXPECTED_TYPES


@pytest.mark.parametrize("fixture", fixture_files(), ids=lambda p: p.stem)
def test_fixture_validates_against_schema(fixture: Path):
    schema = load_schema()
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    data = json.loads(fixture.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    assert not errors, f"{fixture.name}: " + "; ".join(e.message for e in errors)

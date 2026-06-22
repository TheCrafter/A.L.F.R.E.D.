import json
from pathlib import Path

from jsonschema.validators import Draft202012Validator

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "protocol.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_is_valid_2020_12():
    schema = load_schema()
    # Raises jsonschema.exceptions.SchemaError if the schema is itself invalid.
    Draft202012Validator.check_schema(schema)


def test_schema_has_all_thirteen_messages():
    schema = load_schema()
    titles = {d["title"] for d in schema["$defs"].values()}
    expected = {
        "ClientHello", "ServerHello", "StatusRequest", "StatusResponse",
        "CommandSubmit", "CommandAck", "AgentThought", "AgentAction",
        "AgentMessage", "AgentTurnComplete", "KillSwitchActivate",
        "KillSwitchAck", "Error",
    }
    assert expected <= titles
    assert len(schema["oneOf"]) == 13

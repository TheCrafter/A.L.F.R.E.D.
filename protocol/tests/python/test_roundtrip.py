import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from alfred_protocol import Message

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"
ADAPTER = TypeAdapter(Message)


def fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture", fixture_files(), ids=lambda p: p.stem)
def test_fixture_roundtrips_through_pydantic(fixture: Path):
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    model = ADAPTER.validate_python(raw)
    # Dump back to JSON, re-parse: the model must be stable across a round trip.
    reparsed = ADAPTER.validate_json(ADAPTER.dump_json(model))
    assert model == reparsed


@pytest.mark.parametrize("fixture", fixture_files(), ids=lambda p: p.stem)
def test_discriminator_picks_the_right_class(fixture: Path):
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    model = ADAPTER.validate_python(raw)
    # The chosen model's `type` literal must equal the fixture's type field.
    # Message is a RootModel; the concrete instance lives at .root.
    assert model.root.type == raw["type"]

from pathlib import Path

from alfred_brain.memory import MemoryRecord


def test_record_holds_fields():
    r = MemoryRecord(id="a1", text="hi", type="note", tags=["x"],
                     status="active", created="2026-06-23T00:00:00Z", path=Path("p.md"))
    assert r.id == "a1"
    assert r.tags == ["x"]
    assert r.type == "note"

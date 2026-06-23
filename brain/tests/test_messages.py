from datetime import datetime

from alfred_brain.messages import dump, new_id, now_ts
from alfred_protocol import Error


def test_ids_unique():
    assert new_id() != new_id()


def test_ts_is_rfc3339_z():
    ts = now_ts()
    assert ts.endswith("Z")
    datetime.fromisoformat(ts.replace("Z", "+00:00"))  # parses


def test_dump_excludes_none():
    err = Error(v=1, id=new_id(), ts=now_ts(), type="error",
                code="internal", message="boom")  # corr left None
    d = dump(err)
    assert "corr" not in d          # exclude_none drops it
    assert d["type"] == "error"
    assert d["code"] == "internal"

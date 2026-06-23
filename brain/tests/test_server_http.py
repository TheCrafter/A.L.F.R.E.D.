from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def test_status_endpoint_shape():
    app = create_app(Settings(provider="scripted", _env_file=None))
    client = TestClient(app)
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "status.response"
    assert body["corr"] == "http-status"
    assert body["busy"] is False
    assert isinstance(body["active_scopes"], list)
    assert "uptime_seconds" in body
    assert "corr" in body  # present here (not None), so not excluded

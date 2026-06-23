from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.memory import VaultMemory
from alfred_brain.server import create_app
from tests.test_memory_index import FakeEmbedder


def test_memory_tools_registered_and_reload_applies_top_k(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "home"))
    # inject a fake-embedder memory so the test stays offline/deterministic
    mem = VaultMemory(tmp_path / "vault", FakeEmbedder())
    app = create_app(Settings(provider="scripted", _env_file=None), memory=mem)
    # memory tools are available to the agent
    assert app.state.agent._registry.has("remember")
    assert app.state.agent._registry.has("recall")
    assert app.state.agent._registry.has("forget")

    # recall_top_k is hot-reloadable
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        "[memory]\nrecall_top_k = 3\n", encoding="utf-8")
    TestClient(app).post("/config/reload")
    assert app.state.agent._recall_top_k == 3

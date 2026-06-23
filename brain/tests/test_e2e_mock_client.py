import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from alfred_brain.config import Settings
from alfred_brain.server import create_app

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server:
    def __init__(self, port: int):
        app = create_app(Settings(provider="scripted", _env_file=None))
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("brain server did not start")
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.mark.integration
def test_mock_ui_client_drives_real_brain():
    port = _free_port()
    with _Server(port):
        result = subprocess.run(
            ["pnpm", "exec", "tsx", "mock/client.ts", "--url", f"ws://127.0.0.1:{port}/ws"],
            cwd=PROTOCOL, capture_output=True, text=True, timeout=60,
            shell=(sys.platform == "win32"), encoding="utf-8",
        )
    assert result.returncode == 0, f"client failed:\n{result.stdout}\n{result.stderr}"
    assert "turn complete — contract verified end-to-end" in result.stdout
    assert "agent.turn_complete" in result.stdout

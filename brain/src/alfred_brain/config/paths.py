from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    """User-data home for ALFRED ($ALFRED_HOME, default ~/.alfred)."""
    raw = os.environ.get("ALFRED_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".alfred"


def config_path() -> Path:
    return home() / "config.toml"

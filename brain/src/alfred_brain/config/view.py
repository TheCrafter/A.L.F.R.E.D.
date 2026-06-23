from __future__ import annotations

import os
from typing import Any, Mapping

from .paths import config_path
from .settings import ENV_ALIASES, Settings
from .toml_source import read_flat_toml

SECRET_FIELDS = {"groq_api_key", "gemini_api_key"}


def effective_config(settings: Settings, env: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    env = os.environ if env is None else env
    file_data = read_flat_toml(config_path())
    out: dict[str, dict[str, Any]] = {}
    for field in type(settings).model_fields:
        alias = ENV_ALIASES.get(field, field)
        if alias in env:
            source = "env"
        elif field in file_data:
            source = "file"
        else:
            source = "default"
        value = getattr(settings, field)
        if field in SECRET_FIELDS:
            value = "set" if value else "unset"
        out[field] = {"value": value, "source": source}
    return out

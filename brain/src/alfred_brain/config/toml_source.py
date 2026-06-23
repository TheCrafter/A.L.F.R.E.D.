from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

log = logging.getLogger(__name__)

# (toml section, key) -> flat Settings field
SECTION_MAP: dict[tuple[str, str], str] = {
    ("server", "host"): "host",
    ("server", "port"): "port",
    ("reasoning", "provider"): "provider",
    ("reasoning", "groq_api_key"): "groq_api_key",
    ("reasoning", "groq_model"): "groq_model",
    ("reasoning", "gemini_api_key"): "gemini_api_key",
    ("reasoning", "gemini_model"): "gemini_model",
    ("persona", "intensity"): "persona_intensity",
    ("agent", "max_tool_iterations"): "max_tool_iterations",
    ("logging", "level"): "log_level",
    ("memory", "vault_dir"): "memory_vault_dir",
    ("memory", "embed_model"): "memory_embed_model",
    ("memory", "recall_top_k"): "memory_recall_top_k",
}


def read_flat_toml(path: Path) -> dict[str, Any]:
    """Read the sectioned config.toml into flat {field: value}. Missing file -> {}."""
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    flat: dict[str, Any] = {}
    for section, values in raw.items():
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            field = SECTION_MAP.get((section, key))
            if field is None:
                log.warning("unknown config key [%s].%s ignored", section, key)
                continue
            # empty string (e.g. blank api key in the template) means "unset"
            if value == "":
                continue
            flat[field] = value
    return flat


class FlatTomlSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls, path: Path) -> None:
        super().__init__(settings_cls)
        self._data = read_flat_toml(path)

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return dict(self._data)

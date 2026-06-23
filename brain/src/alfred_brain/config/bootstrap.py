from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Mapping

from .paths import config_path

log = logging.getLogger(__name__)


def render_template(env: Mapping[str, str]) -> str:
    from ..providers.registry import GEMINI_MODELS, GROQ_MODELS  # lazy to avoid circular import
    groq_models = " | ".join(GROQ_MODELS)
    gemini_models = " | ".join(GEMINI_MODELS)
    g = env.get
    return f"""# ~/.alfred/config.toml — ALFRED brain config.
# Env vars override any value here (e.g. GROQ_API_KEY). [*] = restart required.

[server]
host = "{g("ALFRED_HOST", "127.0.0.1")}"   # [*] bind address
port = {g("ALFRED_PORT", "8766")}          # [*] 1-65535

[reasoning]
provider = "{g("ALFRED_PROVIDER", "gemini")}"                  # groq | gemini | scripted   (hot-reloadable)
groq_api_key = "{g("GROQ_API_KEY", "")}"            # from https://console.groq.com/keys
groq_model = "{g("GROQ_MODEL", "llama-3.3-70b-versatile")}"   # {groq_models}
gemini_api_key = "{g("GEMINI_API_KEY", "")}"        # from https://aistudio.google.com/apikey
gemini_model = "{g("GEMINI_MODEL", "gemini-2.5-flash")}"   # {gemini_models}   (free tier)

[persona]
intensity = "{g("ALFRED_PERSONA_INTENSITY", "full")}"   # full | light | off   (hot-reloadable)

[agent]
max_tool_iterations = {g("ALFRED_MAX_TOOL_ITERATIONS", "5")}   # integer >= 1   (hot-reloadable)

[logging]
level = "{g("ALFRED_LOG_LEVEL", "INFO")}"   # DEBUG | INFO | WARNING | ERROR | CRITICAL   (hot-reloadable)

[memory]
# vault_dir = ""   # [*] default: $ALFRED_HOME/vault  (an Obsidian-compatible vault)
embed_model = "{g("ALFRED_EMBED_MODEL", "BAAI/bge-small-en-v1.5")}"   # [*] local CPU embedding model
recall_top_k = {g("ALFRED_RECALL_TOP_K", "5")}   # integer >= 1   (hot-reloadable)
"""


def bootstrap_config(env: Mapping[str, str] | None = None) -> Path:
    """Create $ALFRED_HOME/config.toml from a seeded template if missing."""
    env = os.environ if env is None else env
    path = config_path()
    if path.exists():
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_template(env), encoding="utf-8")
        log.info("wrote default config to %s", path)
    except OSError as exc:
        log.warning("could not write config %s: %s; running on defaults + env", path, exc)
    return path

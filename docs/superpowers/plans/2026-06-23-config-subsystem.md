# Config Subsystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the brain a user-owned TOML config file at `$ALFRED_HOME/config.toml` with env-wins precedence, first-run bootstrap seeded from the environment, validated settings, runtime reload of hot fields, and redacted admin visibility.

**Architecture:** Evolve `brain/src/alfred_brain/config.py` into a small `config` package. `Settings` stays **flat** (current field names unchanged); a custom `pydantic-settings` source reads the **sectioned** TOML and flattens `[section].key → flat_field`. Bootstrap writes a documented, env-seeded template on first run. Two off-contract admin HTTP endpoints (`GET /config`, `POST /config/reload`) sit alongside `/status` and `/models`; reload applies hot fields through small `AgentLoop` setters.

**Tech Stack:** Python 3.12, `pydantic` / `pydantic-settings` v2, stdlib `tomllib`, FastAPI, `uv`, pytest.

## Global Constraints

- Python 3.12, managed by `uv`; run from inside `brain/` with `uv run …`.
- The frozen `protocol/` WS contract is **never** touched; config is admin HTTP only.
- Precedence is `defaults → config.toml → env vars` (env wins).
- `$ALFRED_HOME` defaults to `~/.alfred`; the config file is `$ALFRED_HOME/config.toml`.
- Secrets (`groq_api_key`, `gemini_api_key`) are never logged or returned unredacted.
- Existing env var names stay valid via field aliases; existing 52 brain tests stay green.
- Commit messages: conventional, scoped (`feat(brain): …`), **no** `Co-Authored-By` / "authored by Claude" trailer.
- MARK labeling is **out of scope** for this plan (tracked separately).

---

### Task 1: Config package skeleton — flat `Settings` + paths + test isolation

Convert the `config.py` module into a `config/` package, keep `Settings` flat but add `log_level`, validated `Literal`s and numeric bounds, the `$ALFRED_HOME` path helpers, and a pytest fixture that isolates every test from the real `~/.alfred`.

**Files:**
- Delete: `brain/src/alfred_brain/config.py`
- Create: `brain/src/alfred_brain/config/__init__.py`
- Create: `brain/src/alfred_brain/config/paths.py`
- Create: `brain/src/alfred_brain/config/settings.py`
- Create: `brain/tests/conftest.py`
- Modify: `brain/tests/test_config.py` (existing `test_kwargs_override` uses `port=0`, now invalid)

**Interfaces:**
- Produces: `home() -> pathlib.Path`, `config_path() -> pathlib.Path` (in `paths.py`).
- Produces: `Settings` (flat fields: `provider, gemini_api_key, gemini_model, groq_api_key, groq_model, host, port, persona_intensity, max_tool_iterations, log_level`), re-exported from `alfred_brain.config` so `from .config import Settings` keeps working.
- Produces: `ENV_ALIASES: dict[str, str]` (field → env var name) in `settings.py`.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_config.py` (replace file)

```python
import pytest
from pydantic import ValidationError

from alfred_brain.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.provider == "gemini"
    assert s.port == 8766
    assert s.persona_intensity == "full"
    assert s.max_tool_iterations == 5
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    monkeypatch.setenv("ALFRED_PORT", "9999")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setenv("ALFRED_LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.provider == "scripted"
    assert s.port == 9999
    assert s.gemini_api_key == "secret"
    assert s.log_level == "DEBUG"


def test_kwargs_override():
    s = Settings(provider="scripted", port=1234, _env_file=None)
    assert s.provider == "scripted"
    assert s.port == 1234


def test_invalid_enum_rejected():
    with pytest.raises(ValidationError):
        Settings(persona_intensity="ful", _env_file=None)


def test_invalid_port_rejected():
    with pytest.raises(ValidationError):
        Settings(port=0, _env_file=None)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_config.py -q`
Expected: FAIL — `log_level` missing / import errors.

- [ ] **Step 3: Create `paths.py`**

```python
from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    """User-data home for ALFRED ($ALFRED_HOME, default ~/.alfred)."""
    raw = os.environ.get("ALFRED_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".alfred"


def config_path() -> Path:
    return home() / "config.toml"
```

- [ ] **Step 4: Create `settings.py`** (flat fields + Literals + bounds + aliases)

```python
from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# field -> environment variable name (kept explicit; reused by the effective view).
ENV_ALIASES = {
    "provider": "ALFRED_PROVIDER",
    "gemini_api_key": "GEMINI_API_KEY",
    "gemini_model": "GEMINI_MODEL",
    "groq_api_key": "GROQ_API_KEY",
    "groq_model": "GROQ_MODEL",
    "host": "ALFRED_HOST",
    "port": "ALFRED_PORT",
    "persona_intensity": "ALFRED_PERSONA_INTENSITY",
    "max_tool_iterations": "ALFRED_MAX_TOOL_ITERATIONS",
    "log_level": "ALFRED_LOG_LEVEL",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    provider: Literal["gemini", "groq", "scripted"] = Field(
        default="gemini", validation_alias="ALFRED_PROVIDER")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_MODEL")
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", validation_alias="GROQ_MODEL")
    host: str = Field(default="127.0.0.1", validation_alias="ALFRED_HOST")
    port: int = Field(default=8766, ge=1, le=65535, validation_alias="ALFRED_PORT")
    persona_intensity: Literal["full", "light", "off"] = Field(
        default="full", validation_alias="ALFRED_PERSONA_INTENSITY")
    max_tool_iterations: int = Field(
        default=5, ge=1, validation_alias="ALFRED_MAX_TOOL_ITERATIONS")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="ALFRED_LOG_LEVEL")
```

- [ ] **Step 5: Create `config/__init__.py`** (re-export to preserve `from .config import Settings`)

```python
from .paths import config_path, home
from .settings import ENV_ALIASES, Settings

__all__ = ["Settings", "ENV_ALIASES", "home", "config_path"]
```

- [ ] **Step 6: Delete the old module**

```bash
git rm brain/src/alfred_brain/config.py
```

- [ ] **Step 7: Create `tests/conftest.py`** — isolate every test from the real `~/.alfred`

```python
import pytest


@pytest.fixture(autouse=True)
def isolate_alfred_home(tmp_path, monkeypatch):
    """Point $ALFRED_HOME at an empty temp dir so no test reads/writes ~/.alfred."""
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    yield
```

- [ ] **Step 8: Run the whole brain suite**

Run: `cd brain && uv run pytest -q`
Expected: PASS (52 prior + new config assertions; the autouse fixture keeps everything isolated).

- [ ] **Step 9: Commit**

```bash
git add brain/src/alfred_brain/config brain/tests/conftest.py brain/tests/test_config.py
git rm brain/src/alfred_brain/config.py
git commit -m "refactor(brain): config package — validated flat Settings, ALFRED_HOME paths, test isolation"
```

---

### Task 2: Section-flattening TOML source

Read the sectioned `config.toml` and feed it to `Settings` as flat values, ordered **below** env (env wins). Tolerate unknown keys with a warning.

**Files:**
- Create: `brain/src/alfred_brain/config/toml_source.py`
- Modify: `brain/src/alfred_brain/config/settings.py` (add `settings_customise_sources`)
- Test: `brain/tests/test_config_toml.py`

**Interfaces:**
- Consumes: `config_path()` (Task 1), `Settings` (Task 1).
- Produces: `FlatTomlSource` (a `PydanticBaseSettingsSource`); `SECTION_MAP: dict[tuple[str,str], str]` (toml `(section,key) → flat field`).

- [ ] **Step 1: Write the failing test** — `brain/tests/test_config_toml.py`

```python
from pathlib import Path

from alfred_brain.config import Settings


def _write(tmp_path: Path, body: str) -> None:
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(body, encoding="utf-8")


def test_file_values_load_and_flatten(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    _write(tmp_path, """
[server]
port = 9100
[reasoning]
provider = "scripted"
[persona]
intensity = "light"
[logging]
level = "WARNING"
""")
    s = Settings(_env_file=None)
    assert s.port == 9100
    assert s.provider == "scripted"
    assert s.persona_intensity == "light"
    assert s.log_level == "WARNING"


def test_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    _write(tmp_path, "[reasoning]\nprovider = \"scripted\"\n")
    monkeypatch.setenv("ALFRED_PROVIDER", "groq")
    s = Settings(_env_file=None)
    assert s.provider == "groq"  # env wins over file


def test_unknown_keys_tolerated(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "alfred-home"))
    _write(tmp_path, "[mystery]\nwidgets = 3\n[reasoning]\nprovider = \"scripted\"\n")
    s = Settings(_env_file=None)  # must not raise
    assert s.provider == "scripted"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_config_toml.py -q`
Expected: FAIL — file values ignored (no TOML source wired yet).

- [ ] **Step 3: Create `toml_source.py`**

```python
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
}


def read_flat_toml(path: Path) -> dict[str, Any]:
    """Read the sectioned config.toml into flat {field: value}. Missing file -> {}."""
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    flat: dict[str, Any] = {}
    known = set(SECTION_MAP)
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
```

- [ ] **Step 4: Wire the source into `settings.py`** — add to the `Settings` class

```python
    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        from .paths import config_path
        from .toml_source import FlatTomlSource

        # highest priority first: init > env > .env > config.toml > field defaults
        return (init_settings, env_settings, dotenv_settings,
                FlatTomlSource(settings_cls, config_path()), file_secret_settings)
```

- [ ] **Step 5: Run the test**

Run: `cd brain && uv run pytest tests/test_config_toml.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite (no regressions)**

Run: `cd brain && uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add brain/src/alfred_brain/config/toml_source.py brain/src/alfred_brain/config/settings.py brain/tests/test_config_toml.py
git commit -m "feat(brain): load sectioned config.toml (flattened, below env in precedence)"
```

---

### Task 3: First-run bootstrap (env-seeded, documented template)

Write a documented `config.toml` on first run, pre-filled from the current environment; never overwrite an existing file; survive an unwritable home.

**Files:**
- Create: `brain/src/alfred_brain/config/bootstrap.py`
- Modify: `brain/src/alfred_brain/config/__init__.py` (export `bootstrap_config`, `render_template`)
- Test: `brain/tests/test_config_bootstrap.py`

**Interfaces:**
- Consumes: `config_path()`, `home()`, `GROQ_MODELS`/`GEMINI_MODELS` (from `alfred_brain.providers.registry`).
- Produces: `render_template(env: Mapping[str, str]) -> str`; `bootstrap_config(env: Mapping[str, str] | None = None) -> pathlib.Path`.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_config_bootstrap.py`

```python
from pathlib import Path

from alfred_brain.config import bootstrap_config, render_template


def test_template_documents_allowed_values_and_catalog():
    body = render_template({})
    assert "full | light | off" in body
    assert "groq | gemini | scripted" in body
    assert "llama-3.3-70b-versatile" in body   # from the registry catalog
    assert "gemini-2.5-flash" in body
    assert "DEBUG | INFO | WARNING | ERROR | CRITICAL" in body


def test_bootstrap_writes_seeded_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "h"))
    monkeypatch.setenv("ALFRED_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_seeded")
    path = bootstrap_config()
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'provider = "groq"' in text
    assert "gsk_seeded" in text


def test_bootstrap_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_HOME", str(tmp_path / "h"))
    path = (tmp_path / "h")
    path.mkdir(parents=True)
    (path / "config.toml").write_text("[reasoning]\nprovider = \"scripted\"\n", encoding="utf-8")
    bootstrap_config()
    assert 'provider = "scripted"' in (path / "config.toml").read_text(encoding="utf-8")


def test_bootstrap_survives_unwritable_home(tmp_path, monkeypatch):
    # point home at a path whose parent is a file -> mkdir fails
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(blocker / "nested"))
    bootstrap_config()  # must not raise
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_config_bootstrap.py -q`
Expected: FAIL — `bootstrap_config` / `render_template` not importable.

- [ ] **Step 3: Create `bootstrap.py`**

```python
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Mapping

from ..providers.registry import GEMINI_MODELS, GROQ_MODELS
from .paths import config_path

log = logging.getLogger(__name__)


def render_template(env: Mapping[str, str]) -> str:
    groq_models = " | ".join(GROQ_MODELS)
    gemini_models = " | ".join(GEMINI_MODELS)
    g = env.get
    return f"""# ~/.alfred/config.toml — ALFRED brain config.
# Env vars override any value here (e.g. GROQ_API_KEY). [*] = restart required.

[server]
host = "{g("ALFRED_HOST", "127.0.0.1")}"   # [*] bind address
port = {g("ALFRED_PORT", "8766")}          # [*] 1-65535

[reasoning]
provider = "{g("ALFRED_PROVIDER", "gemini")}"                  # {' | '.join(['groq', 'gemini', 'scripted'])}   (hot-reloadable)
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
```

- [ ] **Step 4: Export from `config/__init__.py`**

```python
from .bootstrap import bootstrap_config, render_template
from .paths import config_path, home
from .settings import ENV_ALIASES, Settings

__all__ = ["Settings", "ENV_ALIASES", "home", "config_path",
           "bootstrap_config", "render_template"]
```

- [ ] **Step 5: Run the test**

Run: `cd brain && uv run pytest tests/test_config_bootstrap.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/config/bootstrap.py brain/src/alfred_brain/config/__init__.py brain/tests/test_config_bootstrap.py
git commit -m "feat(brain): first-run config bootstrap (env-seeded, documented, never overwrites)"
```

---

### Task 4: Effective-config view (redacted, per-field source)

Produce the data for `GET /config`: each field's value (secrets redacted) and where it came from (`default | file | env`).

**Files:**
- Create: `brain/src/alfred_brain/config/view.py`
- Modify: `brain/src/alfred_brain/config/__init__.py` (export `effective_config`)
- Test: `brain/tests/test_config_view.py`

**Interfaces:**
- Consumes: `Settings`, `ENV_ALIASES` (Task 1), `read_flat_toml` + `config_path` (Task 2).
- Produces: `effective_config(settings: Settings, env: Mapping[str, str] | None = None) -> dict[str, dict]` — `{field: {"value": ..., "source": "default|file|env"}}`, with `groq_api_key`/`gemini_api_key` values rendered as `"set"`/`"unset"`.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_config_view.py`

```python
from pathlib import Path

from alfred_brain.config import Settings, effective_config


def test_redacts_secrets_and_reports_sources(tmp_path, monkeypatch):
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True)
    (home / "config.toml").write_text("[persona]\nintensity = \"light\"\n", encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(home))
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret")

    s = Settings(_env_file=None)
    view = effective_config(s)

    assert view["groq_api_key"]["value"] == "set"        # redacted, not the key
    assert "gsk_secret" not in str(view)
    assert view["gemini_api_key"]["value"] == "unset"
    assert view["provider"]["source"] == "env"           # env var set
    assert view["persona_intensity"]["source"] == "file" # only in the file
    assert view["port"]["source"] == "default"           # nowhere set
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_config_view.py -q`
Expected: FAIL — `effective_config` not importable.

- [ ] **Step 3: Create `view.py`**

```python
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
```

- [ ] **Step 4: Export from `config/__init__.py`** (add the import + `__all__` entry)

```python
from .view import effective_config
# ... add "effective_config" to __all__
```

- [ ] **Step 5: Run the test**

Run: `cd brain && uv run pytest tests/test_config_view.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/config/view.py brain/src/alfred_brain/config/__init__.py brain/tests/test_config_view.py
git commit -m "feat(brain): effective-config view with secret redaction and per-field source"
```

---

### Task 5: `AgentLoop` hot setters + `GET /config` endpoint

Add the setters reload needs, and expose the read-only config view over HTTP.

**Files:**
- Modify: `brain/src/alfred_brain/agent.py` (add `set_system`, `set_max_iterations`)
- Modify: `brain/src/alfred_brain/server.py` (import `effective_config`; add `GET /config`)
- Test: `brain/tests/test_agent_loop.py` (setter tests), `brain/tests/test_config_endpoint.py`

**Interfaces:**
- Consumes: `effective_config` (Task 4), the live `settings` held in `create_app`.
- Produces: `AgentLoop.set_system(system: str) -> None`, `AgentLoop.set_max_iterations(n: int) -> None`; `GET /config` → `{"config": <effective_config>}`.

- [ ] **Step 1: Write the failing tests**

`brain/tests/test_agent_loop.py` (append):

```python
def test_agent_setters_mutate_config():
    from alfred_brain.providers.scripted import ScriptedProvider
    loop = AgentLoop(ScriptedProvider(), _registry(), "old", max_iterations=5)
    loop.set_system("new system")
    loop.set_max_iterations(2)
    assert loop._system == "new system"
    assert loop._max_iterations == 2
```

`brain/tests/test_config_endpoint.py` (new):

```python
from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def test_get_config_redacts_and_reports(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret")
    app = create_app(Settings(provider="scripted", _env_file=None))
    body = TestClient(app).get("/config").json()["config"]
    assert body["groq_api_key"]["value"] == "set"
    assert "gsk_secret" not in str(body)
    assert body["provider"]["value"] == "scripted"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd brain && uv run pytest tests/test_agent_loop.py::test_agent_setters_mutate_config tests/test_config_endpoint.py -q`
Expected: FAIL — setters / endpoint missing.

- [ ] **Step 3: Add the setters** — `brain/src/alfred_brain/agent.py`, after `set_provider`

```python
    def set_system(self, system: str) -> None:
        self._system = system

    def set_max_iterations(self, n: int) -> None:
        self._max_iterations = n
```

- [ ] **Step 4: Add `GET /config`** — `brain/src/alfred_brain/server.py`

Add the import near the other config import:

```python
from .config import Settings, effective_config
```

Add the endpoint next to the `/models` GET (inside `create_app`):

```python
    @app.get("/config")
    def get_config() -> dict:
        return {"config": effective_config(state["settings"])}
```

Where `state` is a mutable holder created right after `app.state.agent = agent`:

```python
    state = {"settings": settings}
```

(Task 6 reuses `state["settings"]` for reload.)

- [ ] **Step 5: Run the tests**

Run: `cd brain && uv run pytest tests/test_agent_loop.py tests/test_config_endpoint.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/agent.py brain/src/alfred_brain/server.py brain/tests/test_agent_loop.py brain/tests/test_config_endpoint.py
git commit -m "feat(brain): GET /config endpoint + AgentLoop hot setters"
```

---

### Task 6: `POST /config/reload`

Re-read config from disk, apply hot fields to the live brain, report startup-only fields as pending, and reject invalid config without disturbing the running config.

**Files:**
- Modify: `brain/src/alfred_brain/server.py` (add `POST /config/reload` + `_apply_hot`)
- Test: `brain/tests/test_config_reload.py`

**Interfaces:**
- Consumes: `Settings` (re-read), `build_provider` (existing), `system_prompt` (existing), `AgentLoop.set_provider/set_system/set_max_iterations` (Tasks 5), the `state["settings"]` holder and `current` model dict (Task "models endpoint", already in `server.py`).
- Produces: `POST /config/reload` → `{"changed": [...], "startup_only_pending": [...], "config": <effective_config>}`; HTTP 400 on invalid config.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_config_reload.py`

```python
from pathlib import Path

from fastapi.testclient import TestClient

from alfred_brain.config import Settings
from alfred_brain.server import create_app


def _write_home(monkeypatch, tmp_path, body: str) -> None:
    home = tmp_path / "alfred-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(body, encoding="utf-8")
    monkeypatch.setenv("ALFRED_HOME", str(home))


def test_reload_applies_hot_fields(tmp_path, monkeypatch):
    app = create_app(Settings(provider="scripted", persona_intensity="full", _env_file=None))
    client = TestClient(app)
    _write_home(monkeypatch, tmp_path,
                "[persona]\nintensity = \"off\"\n[agent]\nmax_tool_iterations = 2\n")
    body = client.post("/config/reload").json()
    assert "persona_intensity" in body["changed"]
    assert "max_tool_iterations" in body["changed"]
    assert app.state.agent._max_iterations == 2


def test_reload_reports_startup_only_pending(tmp_path, monkeypatch):
    app = create_app(Settings(port=8766, _env_file=None))
    client = TestClient(app)
    _write_home(monkeypatch, tmp_path, "[server]\nport = 9123\n")
    body = client.post("/config/reload").json()
    assert "port" in body["startup_only_pending"]


def test_invalid_reload_is_rejected_and_keeps_old(tmp_path, monkeypatch):
    app = create_app(Settings(persona_intensity="full", _env_file=None))
    client = TestClient(app)
    _write_home(monkeypatch, tmp_path, "[persona]\nintensity = \"bogus\"\n")
    resp = client.post("/config/reload")
    assert resp.status_code == 400
    # unchanged
    assert app.state.agent._system  # still the original system prompt
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_config_reload.py -q`
Expected: FAIL — endpoint missing.

- [ ] **Step 3: Add reload to `server.py`**

Add imports near the top (alongside existing ones):

```python
from pydantic import ValidationError
from .persona import system_prompt
```

(`system_prompt` and `build_provider` are already imported; add only what's missing.)

Inside `create_app`, after the `/config` GET, add:

```python
    HOT_PROVIDER_FIELDS = ("provider", "groq_model", "gemini_model",
                           "groq_api_key", "gemini_api_key")
    STARTUP_ONLY = ("host", "port")

    def _apply_hot(old: Settings, new: Settings) -> tuple[list[str], list[str]]:
        changed: list[str] = []
        if any(getattr(old, f) != getattr(new, f) for f in HOT_PROVIDER_FIELDS):
            new_provider = build_provider(new)
            agent.set_provider(new_provider)
            current["provider"] = new_provider.name
            current["model"] = _model_for(new_provider)
            changed.append("provider")
        if old.persona_intensity != new.persona_intensity:
            agent.set_system(system_prompt(new.persona_intensity))
            changed.append("persona_intensity")
        if old.max_tool_iterations != new.max_tool_iterations:
            agent.set_max_iterations(new.max_tool_iterations)
            changed.append("max_tool_iterations")
        if old.log_level != new.log_level:
            logging.getLogger("alfred_brain").setLevel(new.log_level)
            changed.append("log_level")
        pending = [f for f in STARTUP_ONLY if getattr(old, f) != getattr(new, f)]
        return changed, pending

    @app.post("/config/reload")
    def reload_config() -> dict:
        try:
            new = Settings()
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        changed, pending = _apply_hot(state["settings"], new)
        state["settings"] = new
        return {"changed": changed, "startup_only_pending": pending,
                "config": effective_config(new)}
```

Add `import logging` at the top of `server.py` if not present.

- [ ] **Step 4: Run the test**

Run: `cd brain && uv run pytest tests/test_config_reload.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `cd brain && uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brain/src/alfred_brain/server.py brain/tests/test_config_reload.py
git commit -m "feat(brain): POST /config/reload — apply hot fields, report startup-only, reject invalid"
```

---

### Task 7: Wire bootstrap into startup + docs

Bootstrap the config on real startup, and update the docs/example to point at the new config file.

**Files:**
- Modify: `brain/src/alfred_brain/__main__.py` (bootstrap + load before serving)
- Modify: `brain/README.md` (config-file section)
- Modify: `brain/.env.example` (note it's now optional; config.toml is primary)
- Test: `brain/tests/test_main_bootstrap.py`

**Interfaces:**
- Consumes: `bootstrap_config` (Task 3), `Settings` (Task 1).
- Produces: `alfred_brain.__main__.load_settings(*, bootstrap: bool = True) -> Settings`.

- [ ] **Step 1: Write the failing test** — `brain/tests/test_main_bootstrap.py`

```python
from alfred_brain.__main__ import load_settings


def test_load_settings_bootstraps_then_reads(tmp_path, monkeypatch):
    home = tmp_path / "alfred-home"
    monkeypatch.setenv("ALFRED_HOME", str(home))
    monkeypatch.setenv("ALFRED_PROVIDER", "scripted")
    settings = load_settings()
    assert (home / "config.toml").is_file()      # bootstrap ran
    assert settings.provider == "scripted"        # env still wins
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd brain && uv run pytest tests/test_main_bootstrap.py -q`
Expected: FAIL — `load_settings` not defined.

- [ ] **Step 3: Update `__main__.py`**

```python
import uvicorn

from .config import Settings, bootstrap_config
from .server import create_app


def load_settings(*, bootstrap: bool = True) -> Settings:
    if bootstrap:
        bootstrap_config()
    return Settings()


def main() -> None:
    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test**

Run: `cd brain && uv run pytest tests/test_main_bootstrap.py -q`
Expected: PASS.

- [ ] **Step 5: Update docs** — `brain/README.md`, replace the Run/Configuration intro to mention the config file

In the **Run** section, after the code block, add:

```markdown
On first launch the brain creates `~/.alfred/config.toml` (seeded from any env
vars / `.env` present) and reads config from there. Env vars override the file.
`GET /config` shows the effective config (secrets redacted) with each value's
source; `POST /config/reload` re-applies hot fields (provider/model, persona,
agent iterations, log level) without a restart. `host`/`port` need a restart.
Set `ALFRED_HOME` to relocate the config + vault home (default `~/.alfred`).
```

In `brain/.env.example`, add a top comment line:

```
# Optional for development. The primary config is ~/.alfred/config.toml
# (auto-created on first run, seeded from these values). Env vars override it.
```

- [ ] **Step 6: Run the whole suite**

Run: `cd brain && uv run pytest -q`
Expected: PASS (all prior + new config tests).

- [ ] **Step 7: Commit**

```bash
git add brain/src/alfred_brain/__main__.py brain/README.md brain/.env.example brain/tests/test_main_bootstrap.py
git commit -m "feat(brain): bootstrap config on startup; document the config file"
```

---

## Self-Review

**Spec coverage:**
- §3 home/location → Task 1 (`paths.py`). ✅
- §4 format/structure + documented template → Task 3 (`render_template`). ✅
- §5 precedence + flat Settings + flattening + Literals/aliases → Tasks 1–2. ✅
- §6 bootstrap (seed from env, never overwrite, survive unwritable) → Task 3. ✅
- §7 reload (hot vs startup-only, reject invalid) → Task 6. ✅
- §8 admin endpoints (`GET /config` redacted + source; `POST /config/reload`) → Tasks 4–6. ✅
- §9 validation/errors (startup fail-fast via Literals/bounds; reload reject; unknown-key tolerance) → Tasks 1, 2, 6. ✅
- §10 code shape (config package) → Tasks 1–4. ✅
- §11 testing (temp ALFRED_HOME) → conftest (Task 1) + per-task tests. ✅
- §12 MARK labeling → explicitly out of scope. ✅

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `Settings` flat field names are used identically across tasks; `read_flat_toml`/`SECTION_MAP` (Task 2) reused in Task 4; `effective_config` signature consistent (Tasks 4–6); `_apply_hot`/`current`/`state["settings"]` consistent within Task 6 and reuse the `current` dict + `_model_for` already in `server.py` from the models-endpoint work.

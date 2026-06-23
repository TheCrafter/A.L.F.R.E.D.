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
    "memory_vault_dir": "ALFRED_VAULT_DIR",
    "memory_embed_model": "ALFRED_EMBED_MODEL",
    "memory_recall_top_k": "ALFRED_RECALL_TOP_K",
    "memory_window_messages": "ALFRED_WINDOW_MESSAGES",
    "memory_extract_model": "ALFRED_EXTRACT_MODEL",
    "memory_extract_recall_k": "ALFRED_EXTRACT_RECALL_K",
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
    groq_model: str = Field(default="openai/gpt-oss-20b", validation_alias="GROQ_MODEL")
    host: str = Field(default="127.0.0.1", validation_alias="ALFRED_HOST")
    port: int = Field(default=8766, ge=1, le=65535, validation_alias="ALFRED_PORT")
    persona_intensity: Literal["full", "light", "off"] = Field(
        default="full", validation_alias="ALFRED_PERSONA_INTENSITY")
    max_tool_iterations: int = Field(
        default=5, ge=1, validation_alias="ALFRED_MAX_TOOL_ITERATIONS")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="ALFRED_LOG_LEVEL")
    memory_vault_dir: str | None = Field(default=None, validation_alias="ALFRED_VAULT_DIR")
    memory_embed_model: str = Field(
        default="BAAI/bge-small-en-v1.5", validation_alias="ALFRED_EMBED_MODEL")
    memory_recall_top_k: int = Field(
        default=5, ge=1, validation_alias="ALFRED_RECALL_TOP_K")
    memory_window_messages: int = Field(
        default=20, ge=2, validation_alias="ALFRED_WINDOW_MESSAGES")
    memory_extract_model: str = Field(default="", validation_alias="ALFRED_EXTRACT_MODEL")
    memory_extract_recall_k: int = Field(
        default=5, ge=1, validation_alias="ALFRED_EXTRACT_RECALL_K")

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        from .paths import config_path
        from .toml_source import FlatTomlSource

        # highest priority first: init > env > .env > config.toml > field defaults
        return (init_settings, env_settings, dotenv_settings,
                FlatTomlSource(settings_cls, config_path()), file_secret_settings)

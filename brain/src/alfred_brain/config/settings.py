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

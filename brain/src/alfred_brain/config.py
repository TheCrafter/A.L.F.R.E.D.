from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    provider: str = Field(default="gemini", validation_alias="ALFRED_PROVIDER")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", validation_alias="GEMINI_MODEL")
    host: str = Field(default="127.0.0.1", validation_alias="ALFRED_HOST")
    port: int = Field(default=8766, validation_alias="ALFRED_PORT")
    persona_intensity: str = Field(default="full", validation_alias="ALFRED_PERSONA_INTENSITY")
    max_tool_iterations: int = Field(default=5, validation_alias="ALFRED_MAX_TOOL_ITERATIONS")

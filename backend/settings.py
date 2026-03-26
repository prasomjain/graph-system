from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openai/gpt-3.5-turbo", alias="OPENROUTER_MODEL")
    llm_timeout_seconds: int = Field(default=25, alias="LLM_TIMEOUT_SECONDS")
    graph_data_path: str = Field(
        default=str(Path(__file__).resolve().parents[1] / "frontend" / "src" / "assets" / "processed_graph.json"),
        alias="GRAPH_DATA_PATH",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

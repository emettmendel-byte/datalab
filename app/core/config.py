from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Data Lab"
    cors_origins: list[str] = ["http://localhost:5173"]

    sqlite_url: str = "sqlite:///./db.sqlite3"

    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    local_storage_dir: str = ".local_storage"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"


settings = Settings()


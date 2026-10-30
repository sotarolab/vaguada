"""Settings, read from the environment once and validated.

Every other module takes what it needs as arguments. Only entry points (scripts, the
service app) call `settings()`; nothing inside `features/` or `forecast/` reads settings.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str | None = Field(default=None, description="Postgres DSN; None disables it")
    db_schema: str = Field(default="camanchaca_demo", description="Schema holding every table")
    user_agent: str = Field(default="camanchaca-demo/0.1 (research use)")
    http_timeout_s: float = Field(default=30.0, gt=0)
    vendor_api_key: str | None = Field(default=None, description="Vendor feed key; None skips it")


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()

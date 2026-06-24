"""Runtime configuration — environment-driven, SQLite by default.

Every value here is overridable via an ``EMBASSY_``-prefixed environment variable.
The DB is a one-variable swap to Postgres (``EMBASSY_DATABASE_URL``); nothing else
in the codebase assumes SQLite.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBASSY_", env_file=".env", extra="ignore")

    # --- storage -------------------------------------------------------------
    database_url: str = "sqlite:///./embassy.db"

    # --- admin panel auth (HTTP Basic; distinct from player tokens) ----------
    admin_user: str = "admin"
    admin_password: str = "changeme"

    # --- advertised versions (opaque tokens; never parsed) -------------------
    # schema_version is the wire-format version of this service's payload types.
    schema_version: int = 1
    ruleset_version: str = "0.0.0-dev"
    content_version: str = "0.0.0-dev"
    consent_version: str = "1"

    # --- ingest controls -----------------------------------------------------
    enable_ingest: bool = True
    max_batch: int = 100

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()

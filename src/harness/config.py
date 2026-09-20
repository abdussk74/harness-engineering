"""Typed config, loaded from the environment / `.env`.

Every setting is `HARNESS_`-prefixed to stay out of the way of an
agent's own env vars (LLM API keys, etc.), which are the developer's
concern, not the Harness's.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class HarnessConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HARNESS_", env_file=".env", extra="ignore")

    api_token: str | None = None
    """Bearer token required on every request when set. Unset = no auth
    (fine for pure-localhost dev; `harness dev` should set one)."""

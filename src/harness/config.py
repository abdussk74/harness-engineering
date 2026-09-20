"""Typed config, loaded from the environment / `.env`.

Every setting is `HARNESS_`-prefixed to stay out of the way of an
agent's own env vars (LLM API keys, LANGSMITH_*, etc.), which are the
developer's concern, not the Harness's — those are read directly by
LangChain/LangChain provider packages, not through this model.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class HarnessConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HARNESS_", env_file=".env", extra="ignore")

    api_token: str | None = None
    """Bearer token required on every request when set. Unset = no auth
    (fine for pure-localhost dev; `harness dev` should set one)."""

    llm_provider: str | None = None
    """ctx.llm's provider: "anthropic" (default), "openai", or "ollama"."""

    llm_model: str | None = None
    """ctx.llm's model name. Defaults per-provider if unset (required for
    "openai" and "ollama", which have no universal default model)."""

    ollama_base_url: str = "http://localhost:11434"
    """Where ctx.llm reaches a local Ollama server. Inside a `harness dev`
    container this needs to be the host's address, not localhost — see
    the --llm-provider ollama note in `harness dev --help`."""


def load_env_file() -> None:
    """Loads `.env` into the process environment (not just this model's
    own fields) so LangChain's native LANGSMITH_*/provider-API-key env
    var reading — which never goes through HarnessConfig — sees it too.

    `find_dotenv(usecwd=True)` because this always runs from
    `harness/config.py`, a library file — plain `load_dotenv()`'s
    default search walks up from the *caller's* file location via stack
    inspection, which would look near this package's install location,
    never the agent project's own working directory where its `.env`
    actually lives.
    """
    load_dotenv(find_dotenv(usecwd=True))

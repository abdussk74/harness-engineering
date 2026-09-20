"""HarnessConfig and load_env_file(): the latter is what makes
LANGSMITH_*/provider API keys in .env visible to LangChain's own native
env-var reading, which never goes through HarnessConfig at all."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from harness.config import load_env_file


def test_load_env_file_populates_os_environ_not_just_harness_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LANGSMITH_TRACING=true\nLANGSMITH_API_KEY=test-key-123\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)

    try:
        load_env_file()
        assert os.environ.get("LANGSMITH_TRACING") == "true"
        assert os.environ.get("LANGSMITH_API_KEY") == "test-key-123"
    finally:
        # load_dotenv() writes os.environ directly, bypassing monkeypatch's
        # own undo tracking — clean up explicitly so this doesn't leak into
        # other tests.
        os.environ.pop("LANGSMITH_TRACING", None)
        os.environ.pop("LANGSMITH_API_KEY", None)

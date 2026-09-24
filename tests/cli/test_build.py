"""Unit coverage for `harness build`'s codegen and validation.

The actual `docker buildx build` invocation is verified manually (see
the M5 commit message) rather than re-run here — a multi-minute Docker
build doesn't belong in the fast test loop. This file covers what can
be tested quickly: the Dockerfile template and the CLI's error paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_cli.codegen.dockerfile import (
    render_dockerfile,
    render_standalone_dashboard_dockerfile,
    render_standalone_dockerfile,
)
from harness_cli.main import app
from tests.cli._util import squeeze

runner = CliRunner()


def test_render_dockerfile_wires_entrypoint_and_agent_dir() -> None:
    content = render_dockerfile(
        entrypoint="agent:ResearchAgent", agent_dir="examples/research-agent", port=8080
    )

    assert "HARNESS_ENTRYPOINT=agent:ResearchAgent" in content
    assert "COPY examples/research-agent ./agent_src" in content
    assert "USER harness" in content
    assert "HEALTHCHECK" in content
    assert content.count("FROM ") == 3  # builder, dev, runtime


def test_render_standalone_dockerfile_installs_git_before_uv_sync() -> None:
    """a2a-harness resolves from a git dependency in a standalone agent's
    own pyproject.toml — python:3.12-slim doesn't ship git, so uv sync
    fails inside the container without it. Caught live (see the
    code-review-agent build) before this test existed; locking it in
    now so a future template change can't silently drop it."""
    content = render_standalone_dockerfile(entrypoint="agent:CodeReviewAgent", port=8080)

    assert "apt-get install -y --no-install-recommends git" in content
    git_index = content.index("apt-get install")
    sync_index = content.index("uv sync --frozen --no-dev")
    assert git_index < sync_index
    assert "HARNESS_ENTRYPOINT=agent:CodeReviewAgent" in content
    assert "USER harness" in content


def test_render_standalone_dashboard_dockerfile_installs_git_and_pins_ref() -> None:
    content = render_standalone_dashboard_dockerfile(
        git_url="https://github.com/abdussk74/harness-engineering.git", git_ref="v1.1.0"
    )

    assert "apt-get install -y --no-install-recommends git" in content
    git_index = content.index("apt-get install")
    pip_index = content.index("uv pip install")
    assert git_index < pip_index
    expected = "a2a-harness @ git+https://github.com/abdussk74/harness-engineering.git@v1.1.0"
    assert expected in content


def test_render_standalone_dashboard_dockerfile_omits_ref_when_unset() -> None:
    content = render_standalone_dashboard_dockerfile(
        git_url="https://github.com/abdussk74/harness-engineering.git", git_ref=None
    )

    assert "a2a-harness @ git+https://github.com/abdussk74/harness-engineering.git'" in content


def test_build_fails_without_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["build", "--tag", "x:dev"])

    assert result.exit_code != 0
    assert "No pyproject.toml" in squeeze(result.output)


def test_build_fails_without_harness_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["build", "--tag", "x:dev"])

    assert result.exit_code != 0
    assert "tool.harness" in squeeze(result.output)


def test_build_rejects_multi_platform_without_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.harness]\nentrypoint = "agent:X"\n')
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["build", "--tag", "x:dev", "--platform", "linux/amd64,linux/arm64"]
    )

    assert result.exit_code != 0
    assert "--push" in squeeze(result.output)

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

from harness_cli.codegen.dockerfile import render_dockerfile
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

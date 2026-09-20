from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_cli.main import app

runner = CliRunner()


def test_deploy_fails_without_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["deploy", "--target", "local"])

    assert result.exit_code != 0
    assert "No pyproject.toml" in result.output


def test_deploy_rejects_unknown_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.harness]\nentrypoint = "agent:X"\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "harness").mkdir()
    (tmp_path / "src" / "harness" / "__init__.py").write_text("")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["deploy", "--target", "nonsense"])

    assert result.exit_code != 0
    assert "Unknown target" in result.output


def test_deploy_k8s_requires_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.harness]\nentrypoint = "agent:X"\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "harness").mkdir()
    (tmp_path / "src" / "harness" / "__init__.py").write_text("")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["deploy", "--target", "k8s"])

    assert result.exit_code != 0
    assert "--registry" in result.output

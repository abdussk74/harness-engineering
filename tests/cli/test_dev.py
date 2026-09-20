"""Unit coverage for `harness dev`'s validation paths.

The actual `docker compose up` run is verified manually (see the M6
commit message) rather than re-run here for the same reason as
`harness build`: it's slow and stands up real containers, which
doesn't belong in the fast test loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness_cli.main import app

runner = CliRunner()


def test_dev_fails_without_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["dev"])

    assert result.exit_code != 0
    assert "No pyproject.toml" in result.output


def test_dev_fails_without_harness_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["dev"])

    assert result.exit_code != 0
    assert "tool.harness" in result.output

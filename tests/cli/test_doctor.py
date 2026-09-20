from __future__ import annotations

import socket

from typer.testing import CliRunner

from harness_cli.commands.doctor import _check_port
from harness_cli.main import app

runner = CliRunner()


def test_doctor_runs_and_reports_each_check() -> None:
    result = runner.invoke(app, ["doctor"])

    assert "docker" in result.output
    assert "uv" in result.output
    assert result.exit_code in (0, 1)


def test_check_port_detects_port_in_use() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        check = _check_port(port, "test")

    assert check.ok is False
    assert check.required is False


def test_check_port_detects_free_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]

    check = _check_port(free_port, "test")

    assert check.ok is True

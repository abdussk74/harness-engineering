"""`harness doctor` — verify the local environment is ready for A2A agent development."""

from __future__ import annotations

import shutil
import socket
import subprocess
from dataclasses import dataclass

import typer

_DEV_PORTS: dict[int, str] = {
    8080: "agent (harness dev)",
    4317: "OTel collector (OTLP gRPC)",
    4318: "OTel collector (OTLP HTTP)",
    16686: "Jaeger UI",
    3400: "dashboard (harness dev)",
}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _run(cmd: list[str], timeout: float = 5.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return False, f"'{cmd[0]}' not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"'{' '.join(cmd)}' timed out after {timeout}s"

    output = (result.stdout or result.stderr).strip()
    first_line = output.splitlines()[0] if output else ""

    if result.returncode != 0:
        return False, first_line or f"exit code {result.returncode}"
    return True, first_line


def _check_docker_cli() -> Check:
    if shutil.which("docker") is None:
        return Check("docker", False, "not found on PATH — install Docker Desktop or Colima")
    ok, detail = _run(["docker", "--version"])
    return Check("docker", ok, detail)


def _check_docker_daemon() -> Check:
    if shutil.which("docker") is None:
        return Check("docker daemon", False, "skipped — docker CLI not found")
    ok, detail = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10.0)
    if not ok:
        return Check(
            "docker daemon",
            False,
            "docker CLI found but daemon is not reachable — is Docker Desktop or Colima running?",
        )
    return Check("docker daemon", True, f"daemon reachable (server {detail})")


def _check_buildx() -> Check:
    ok, detail = _run(["docker", "buildx", "version"])
    if not ok:
        return Check("docker buildx", False, "not available — required for multi-arch image builds")
    return Check("docker buildx", True, detail)


def _check_compose() -> Check:
    ok, detail = _run(["docker", "compose", "version"])
    if not ok:
        return Check("docker compose", False, "not available — required for `harness dev`")
    return Check("docker compose", True, detail)


def _check_uv() -> Check:
    if shutil.which("uv") is None:
        return Check("uv", False, "not found on PATH — install from https://docs.astral.sh/uv/")
    ok, detail = _run(["uv", "--version"])
    return Check("uv", ok, detail)


def _check_port(port: int, purpose: str) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        in_use = sock.connect_ex(("127.0.0.1", port)) == 0
    if in_use:
        detail = f"already in use — needed for {purpose}"
        return Check(f"port {port}", False, detail, required=False)
    return Check(f"port {port}", True, f"free ({purpose})")


def _check_runtime_context() -> Check:
    ok, detail = _run(["docker", "context", "show"])
    if not ok:
        return Check("docker context", True, "unknown", required=False)
    return Check("docker context", True, f"active context: {detail}", required=False)


def _print(check: Check) -> None:
    if check.ok:
        marker = "[ OK ]"
    elif check.required:
        marker = "[FAIL]"
    else:
        marker = "[WARN]"
    typer.echo(f"{marker} {check.name}: {check.detail}")


def run_checks() -> list[Check]:
    """All environment checks, for `doctor` to print and `dev` to preflight."""
    return [
        _check_docker_cli(),
        _check_docker_daemon(),
        _check_buildx(),
        _check_compose(),
        _check_uv(),
        *(_check_port(port, purpose) for port, purpose in _DEV_PORTS.items()),
        _check_runtime_context(),
    ]


def doctor() -> None:
    """Check that Docker, buildx, compose, uv, and required ports are ready."""
    checks = run_checks()

    for check in checks:
        _print(check)

    failures = [c for c in checks if c.required and not c.ok]
    if failures:
        typer.echo("")
        typer.echo(f"{len(failures)} required check(s) failed — fix these before `harness dev`.")
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("Environment looks ready.")

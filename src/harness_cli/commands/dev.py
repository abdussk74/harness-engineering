"""`harness dev` — runs the agent locally via docker compose, with hot
reload plus a local OTel Collector + Jaeger + dashboard alongside it."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from harness.config import HarnessConfig
from harness_cli.codegen.compose import render_compose, render_otel_collector_config
from harness_cli.codegen.dockerfile import render_dockerfile
from harness_cli.commands.doctor import run_checks
from harness_cli.project import find_workspace_root, read_entrypoint

_AGENT_PORT = 8080
_DASHBOARD_PORT = 3400
_JAEGER_UI_PORT = 16686


def _preflight() -> None:
    failures = [c for c in run_checks() if c.required and not c.ok]
    if not failures:
        return
    typer.echo("Environment isn't ready for `harness dev`:")
    for check in failures:
        typer.echo(f"  [FAIL] {check.name}: {check.detail}")
    typer.echo("\nRun `harness doctor` for the full report.")
    raise typer.Exit(code=1)


def dev(
    detach: bool = typer.Option(
        False, "--detach", "-d", help="Run in the background instead of streaming logs"
    ),
) -> None:
    """Runs the agent in this directory as a container, hot-reloading on
    source changes, alongside a local OTel Collector, Jaeger, and dashboard."""
    project_dir = Path.cwd()
    entrypoint = read_entrypoint(project_dir)
    workspace_root = find_workspace_root(project_dir)
    agent_dir = project_dir.relative_to(workspace_root)
    config = HarnessConfig()

    _preflight()

    harness_dir = workspace_root / ".harness"
    harness_dir.mkdir(exist_ok=True)

    dockerfile_path = harness_dir / f"{project_dir.name}.Dockerfile"
    dockerfile_path.write_text(
        render_dockerfile(entrypoint=entrypoint, agent_dir=str(agent_dir), port=_AGENT_PORT)
    )

    otel_config_path = harness_dir / "otel-collector-config.yaml"
    otel_config_path.write_text(render_otel_collector_config())

    compose_path = harness_dir / f"{project_dir.name}-compose.yml"
    compose_path.write_text(
        render_compose(
            agent_name=project_dir.name,
            workspace_root=workspace_root,
            agent_dir=project_dir,
            agent_dockerfile=dockerfile_path,
            otel_collector_config=otel_config_path,
            agent_port=_AGENT_PORT,
            dashboard_port=_DASHBOARD_PORT,
            api_token=config.api_token,
        )
    )

    typer.echo(f"Agent Card:  http://localhost:{_AGENT_PORT}/.well-known/agent-card.json")
    typer.echo(f"Dashboard:   http://localhost:{_DASHBOARD_PORT}")
    typer.echo(f"Jaeger:      http://localhost:{_JAEGER_UI_PORT}")
    typer.echo("")

    cmd = ["docker", "compose", "-f", str(compose_path), "up", "--build"]
    if detach:
        cmd.append("-d")
    result = subprocess.run(cmd, check=False)  # noqa: S603 - fixed argv, no shell
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)

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

# Docker Desktop's DNS name for reaching the host from inside a
# container; works out of the box on Docker Desktop (Mac/Windows) and
# on Docker 20.10+ with the host-gateway extra_hosts entry. Colima
# needs `colima start --network-address` or an explicit host IP instead
# — not something this CLI can detect, so this is a starting default,
# not a guarantee.
_OLLAMA_HOST_GATEWAY_URL = "http://host.docker.internal:11434"


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
    llm_provider: str = typer.Option(
        None,
        "--llm-provider",
        help="ctx.llm's provider: anthropic (default), openai, or ollama "
        "(develop without spending API tokens, using a local model).",
    ),
) -> None:
    """Runs the agent in this directory as a container, hot-reloading on
    source changes, alongside a local OTel Collector, Jaeger, and dashboard."""
    project_dir = Path.cwd()
    entrypoint = read_entrypoint(project_dir)
    workspace_root = find_workspace_root(project_dir)
    agent_dir = project_dir.relative_to(workspace_root)
    config = HarnessConfig()
    resolved_llm_provider = llm_provider or config.llm_provider
    ollama_base_url = None
    if resolved_llm_provider == "ollama":
        ollama_base_url = (
            _OLLAMA_HOST_GATEWAY_URL
            if config.ollama_base_url == "http://localhost:11434"
            else config.ollama_base_url
        )
        typer.echo(
            f"Using Ollama at {ollama_base_url} — on Colima, override with "
            "HARNESS_OLLAMA_BASE_URL in .env if this isn't reachable from containers.\n"
        )

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
            llm_provider=resolved_llm_provider,
            ollama_base_url=ollama_base_url,
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

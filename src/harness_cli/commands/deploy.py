"""`harness deploy` — builds and ships the agent in the current
directory to either target, behind the same DeployTarget interface."""

from __future__ import annotations

from pathlib import Path

import typer

from harness.config import HarnessConfig
from harness_cli.deploy_targets.base import AgentBuildSpec, DeployConfig, DeployTarget
from harness_cli.deploy_targets.kubernetes import KubernetesDeployTarget
from harness_cli.deploy_targets.local import LocalDeployTarget
from harness_cli.project import find_workspace_root, read_entrypoint

_AGENT_PORT = 8080


def deploy(
    target: str = typer.Option(..., "--target", "-t", help="Where to deploy: local or k8s"),
    registry: str = typer.Option(
        None, "--registry", help="Container registry for --target k8s, e.g. ghcr.io/you"
    ),
    namespace: str = typer.Option(
        None, "--namespace", help="Kubernetes namespace for --target k8s"
    ),
) -> None:
    """Builds and deploys the agent in the current directory."""
    project_dir = Path.cwd()
    entrypoint = read_entrypoint(project_dir)
    workspace_root = find_workspace_root(project_dir)
    spec = AgentBuildSpec(
        name=project_dir.name,
        entrypoint=entrypoint,
        project_dir=project_dir,
        workspace_root=workspace_root,
        port=_AGENT_PORT,
    )
    config = HarnessConfig()
    deploy_env = {"HARNESS_API_TOKEN": config.api_token} if config.api_token else {}

    deploy_target: DeployTarget
    if target == "local":
        deploy_target = LocalDeployTarget()
    elif target == "k8s":
        if not registry:
            raise typer.BadParameter("--target k8s requires --registry (e.g. ghcr.io/you)")
        deploy_target = KubernetesDeployTarget(registry=registry, namespace=namespace)
    else:
        raise typer.BadParameter(f"Unknown target '{target}'; expected 'local' or 'k8s'.")

    typer.echo(f"Building {spec.name} for {target}...")
    build_result = deploy_target.build(spec)
    typer.echo(f"Built {build_result.image}")

    typer.echo(f"Deploying to {target}...")
    result = deploy_target.deploy(build_result, DeployConfig(env=deploy_env))
    typer.echo(f"Deployed: {result.deploy_id} ({result.detail})")

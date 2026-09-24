"""`harness build` — produces the production Docker image for an agent."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from harness_cli.codegen.dockerfile import render_dockerfile, render_standalone_dockerfile
from harness_cli.project import resolve_project


def build(
    tag: str = typer.Option(..., "--tag", "-t", help="Image tag, e.g. research-agent:dev"),
    target: str = typer.Option("runtime", help="Dockerfile stage to build: runtime or dev"),
    platform: str = typer.Option("linux/arm64", help="Target platform(s), comma-separated"),
    push: bool = typer.Option(False, help="Push the image (required for multi-platform builds)"),
) -> None:
    """Builds the agent in the current directory as a production Docker image."""
    if "," in platform and not push:
        raise typer.BadParameter(
            "Multi-platform builds require --push (buildx can't --load more than one platform)."
        )

    project_dir = Path.cwd()
    layout = resolve_project(project_dir)

    if layout.mode == "monorepo":
        dockerfile_content = render_dockerfile(
            entrypoint=layout.entrypoint,
            agent_dir=str(layout.agent_dir_relative_to_context),
        )
    else:
        dockerfile_content = render_standalone_dockerfile(entrypoint=layout.entrypoint)

    harness_dir = layout.build_context / ".harness"
    harness_dir.mkdir(exist_ok=True)
    dockerfile_path = harness_dir / f"{project_dir.name}.Dockerfile"
    dockerfile_path.write_text(dockerfile_content)

    cmd = [
        "docker",
        "buildx",
        "build",
        "--file",
        str(dockerfile_path),
        "--target",
        target,
        "--platform",
        platform,
        "--tag",
        tag,
        "--push" if push else "--load",
        str(layout.build_context),
    ]
    typer.echo(f"Building {tag} (target={target}, platform={platform}, mode={layout.mode})...")
    result = subprocess.run(cmd, check=False)  # noqa: S603 - fixed argv, no shell
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
    typer.echo(f"Built {tag}")

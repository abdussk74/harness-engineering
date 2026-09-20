"""`harness build` — produces the production Docker image for an agent."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import typer

from harness_cli.codegen.dockerfile import render_dockerfile


def _find_workspace_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "harness" / "__init__.py").exists():
            return candidate
    raise typer.BadParameter(
        "Could not find the Harness workspace root (no src/harness/ in any parent directory)."
    )


def _read_entrypoint(project_dir: Path) -> str:
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        raise typer.BadParameter(f"No pyproject.toml in {project_dir}.")
    config = tomllib.loads(pyproject_path.read_text())
    entrypoint = config.get("tool", {}).get("harness", {}).get("entrypoint")
    if not entrypoint:
        raise typer.BadParameter(
            f"{pyproject_path} is missing [tool.harness]\\nentrypoint = 'module:ClassName'"
        )
    return str(entrypoint)


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
    entrypoint = _read_entrypoint(project_dir)
    workspace_root = _find_workspace_root(project_dir)
    agent_dir = project_dir.relative_to(workspace_root)

    dockerfile_content = render_dockerfile(entrypoint=entrypoint, agent_dir=str(agent_dir))
    dockerfile_path = workspace_root / ".harness" / f"{project_dir.name}.Dockerfile"
    dockerfile_path.parent.mkdir(exist_ok=True)
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
        str(workspace_root),
    ]
    typer.echo(f"Building {tag} (target={target}, platform={platform})...")
    result = subprocess.run(cmd, check=False)  # noqa: S603 - fixed argv, no shell
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)
    typer.echo(f"Built {tag}")

"""Shared "what agent am I in?" detection for `build` and `dev`."""

from __future__ import annotations

import tomllib
from pathlib import Path

import typer


def find_workspace_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "harness" / "__init__.py").exists():
            return candidate
    raise typer.BadParameter(
        "Could not find the Harness workspace root (no src/harness/ in any parent directory)."
    )


def read_entrypoint(project_dir: Path) -> str:
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

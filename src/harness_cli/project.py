"""Shared "what agent am I in, and how is it packaged?" detection for
`build`, `dev`, and `deploy`.

Two layouts are supported:

- **monorepo** — the agent lives inside this same workspace (the
  examples/ pattern). `a2a-harness` is installed editable from local
  source, so the Docker build context is the workspace root and the
  image copies `src/` in directly.
- **standalone** — the agent is its own repo, depending on
  `a2a-harness` as a normal (git) dependency declared in its own
  `pyproject.toml`. The Docker build context is the agent's own
  directory; `a2a-harness` is installed from git during the build,
  same as any other dependency, so no local Harness source needs to
  be present at all.

`resolve_project()` picks the mode by whether a Harness workspace root
is findable above the agent directory — an agent explicitly declaring
`a2a-harness` as a dependency while *also* sitting inside a workspace
(unlikely, but possible) is treated as monorepo, since that's the
faster local dev loop for anyone actually working on the platform.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

import typer

DEFAULT_HARNESS_GIT_URL = "https://github.com/abdussk74/harness-engineering.git"
"""Fallback used when a standalone agent's pyproject.toml doesn't
declare a git source for a2a-harness explicitly (e.g. it depends on a
future published package instead) but something — the dashboard build,
the Kubernetes chart fetch — still needs Harness's own repo."""


@dataclass(frozen=True)
class ProjectLayout:
    mode: str
    """"monorepo" or "standalone"."""

    build_context: Path
    """Directory to pass as the Docker build context."""

    project_dir: Path
    """The agent's own directory (where its pyproject.toml lives)."""

    entrypoint: str
    """module:ClassName for the @agent-decorated class."""

    harness_git_url: str | None = None
    """Standalone mode only: the git URL its pyproject.toml declares for
    a2a-harness — reused for the dashboard build so it matches the
    agent's own harness_cli version instead of assuming a fixed repo."""

    harness_git_ref: str | None = None
    """Standalone mode only: the tag/rev/branch pinned alongside
    harness_git_url, if any (None means the remote's default branch)."""

    @property
    def agent_dir_relative_to_context(self) -> Path:
        return self.project_dir.relative_to(self.build_context)


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


def _find_workspace_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "harness" / "__init__.py").exists():
            return candidate
    return None


def _read_harness_git_source(project_dir: Path) -> tuple[str | None, str | None]:
    pyproject_path = project_dir / "pyproject.toml"
    config = tomllib.loads(pyproject_path.read_text())
    source = config.get("tool", {}).get("uv", {}).get("sources", {}).get("a2a-harness", {})
    if not isinstance(source, dict) or "git" not in source:
        return None, None
    ref = source.get("tag") or source.get("rev") or source.get("branch")
    return str(source["git"]), (str(ref) if ref else None)


def fetch_harness_repo_shallow(*, git_url: str, git_ref: str | None, dest: Path) -> Path:
    """Shallow-clones Harness's own repo into `dest`, for standalone-mode
    needs that require files from it directly — the Kubernetes deploy
    target's Helm chart, currently the only caller — rather than
    something installable as a Python dependency. Re-clones on every
    call rather than caching, since correctness (matching the agent's
    pinned ref) matters more than the clone's small cost here."""
    if dest.exists():
        shutil.rmtree(dest)
    cmd = ["git", "clone", "--depth", "1"]
    if git_ref:
        cmd += ["--branch", git_ref]
    cmd += [git_url, str(dest)]
    subprocess.run(cmd, check=True)  # noqa: S603 - fixed argv, no shell
    return dest


def resolve_project(project_dir: Path) -> ProjectLayout:
    entrypoint = read_entrypoint(project_dir)
    workspace_root = _find_workspace_root(project_dir)
    if workspace_root is not None:
        return ProjectLayout(
            mode="monorepo",
            build_context=workspace_root,
            project_dir=project_dir,
            entrypoint=entrypoint,
        )
    harness_git_url, harness_git_ref = _read_harness_git_source(project_dir)
    return ProjectLayout(
        mode="standalone",
        build_context=project_dir,
        project_dir=project_dir,
        entrypoint=entrypoint,
        harness_git_url=harness_git_url,
        harness_git_ref=harness_git_ref,
    )

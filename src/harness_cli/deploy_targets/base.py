"""The DeployTarget interface every backend implements.

Nothing in here assumes a cluster exists, and nothing assumes it's on
a laptop either — that split is the whole point (see
docs/adr/0003-container-deploy-abstraction.md).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AgentBuildSpec:
    """What to build: an agent project's identity."""

    name: str
    entrypoint: str
    project_dir: Path
    workspace_root: Path
    port: int = 8080


@dataclass(frozen=True)
class BuildResult:
    """What a build produced: an image reference."""

    image: str
    port: int


@dataclass(frozen=True)
class DeployConfig:
    """How to deploy it: target-specific knobs the CLI collects."""

    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DeployResult:
    deploy_id: str
    detail: str = ""


@dataclass(frozen=True)
class DeployStatus:
    ready: bool
    detail: str


class DeployTarget(Protocol):
    def build(self, spec: AgentBuildSpec) -> BuildResult: ...
    def deploy(self, build: BuildResult, config: DeployConfig) -> DeployResult: ...
    def status(self, deploy_id: str) -> DeployStatus: ...
    def logs(self, deploy_id: str) -> Iterator[str]: ...
    def teardown(self, deploy_id: str) -> None: ...

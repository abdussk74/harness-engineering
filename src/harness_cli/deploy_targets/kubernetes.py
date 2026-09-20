"""KubernetesDeployTarget: multi-arch build + push, then `helm upgrade
--install` against the generic chart in helm/harness-agent/."""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

from harness_cli.codegen.dockerfile import render_dockerfile
from harness_cli.deploy_targets.base import (
    AgentBuildSpec,
    BuildResult,
    DeployConfig,
    DeployResult,
    DeployStatus,
)


class KubernetesDeployTarget:
    def __init__(
        self,
        *,
        registry: str,
        platform: str = "linux/amd64,linux/arm64",
        namespace: str | None = None,
    ) -> None:
        self._registry = registry.rstrip("/")
        self._platform = platform
        self._namespace = namespace
        self._chart_path: Path | None = None

    def build(self, spec: AgentBuildSpec) -> BuildResult:
        image = f"{self._registry}/{spec.name}:latest"
        dockerfile_path = spec.workspace_root / ".harness" / f"{spec.name}.Dockerfile"
        dockerfile_path.parent.mkdir(exist_ok=True)
        agent_dir = spec.project_dir.relative_to(spec.workspace_root)
        dockerfile_path.write_text(
            render_dockerfile(entrypoint=spec.entrypoint, agent_dir=str(agent_dir), port=spec.port)
        )
        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                "--file",
                str(dockerfile_path),
                "--target",
                "runtime",
                "--platform",
                self._platform,
                "--tag",
                image,
                "--push",
                str(spec.workspace_root),
            ],
            check=True,
        )
        self._chart_path = spec.workspace_root / "helm" / "harness-agent"
        return BuildResult(image=image, port=spec.port)

    def deploy(self, build: BuildResult, config: DeployConfig) -> DeployResult:
        assert self._chart_path is not None, "deploy() called before build()"
        release_name = f"harness-{uuid.uuid4().hex[:8]}"
        repository, _, tag = build.image.rpartition(":")
        cmd = [
            "helm",
            "upgrade",
            "--install",
            release_name,
            str(self._chart_path),
            "--set",
            f"image.repository={repository}",
            "--set",
            f"image.tag={tag}",
            "--set",
            f"port={build.port}",
            "--set",
            f"service.port={build.port}",
        ]
        if self._namespace:
            cmd += ["--namespace", self._namespace, "--create-namespace"]
        for key, value in config.env.items():
            cmd += ["--set", f"env.{key}={value}"]
        subprocess.run(cmd, check=True)
        return DeployResult(deploy_id=release_name, detail=f"helm release '{release_name}'")

    def status(self, deploy_id: str) -> DeployStatus:
        cmd = ["kubectl", "get", "deployment", deploy_id]
        if self._namespace:
            cmd += ["--namespace", self._namespace]
        cmd += ["-o", "jsonpath={.status.readyReplicas}/{.status.replicas}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return DeployStatus(ready=False, detail="not found")
        detail = result.stdout.strip()
        ready_str, _, total_str = detail.partition("/")
        ready = bool(ready_str) and ready_str == total_str
        return DeployStatus(ready=ready, detail=detail or "0/0")

    def logs(self, deploy_id: str) -> Iterator[str]:
        cmd = ["kubectl", "logs", f"deployment/{deploy_id}"]
        if self._namespace:
            cmd += ["--namespace", self._namespace]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        yield from (result.stdout + result.stderr).splitlines()

    def teardown(self, deploy_id: str) -> None:
        cmd = ["helm", "uninstall", deploy_id]
        if self._namespace:
            cmd += ["--namespace", self._namespace]
        subprocess.run(cmd, check=False)

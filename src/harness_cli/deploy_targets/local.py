"""LocalDeployTarget: the production (runtime-stage) image as a plain
container via `docker run` — no hot reload, no telemetry stack (that's
`harness dev`'s job). This is what "deployed, but on my laptop" means.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Iterator

from harness_cli.codegen.dockerfile import render_dockerfile
from harness_cli.deploy_targets.base import (
    AgentBuildSpec,
    BuildResult,
    DeployConfig,
    DeployResult,
    DeployStatus,
)


class LocalDeployTarget:
    def build(self, spec: AgentBuildSpec) -> BuildResult:
        image = f"{spec.name}:local"
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
                "--tag",
                image,
                "--load",
                str(spec.workspace_root),
            ],
            check=True,
        )
        return BuildResult(image=image, port=spec.port)

    def deploy(self, build: BuildResult, config: DeployConfig) -> DeployResult:
        deploy_id = f"harness-{uuid.uuid4().hex[:8]}"
        cmd = ["docker", "run", "-d", "--name", deploy_id, "-p", f"{build.port}:{build.port}"]
        for key, value in config.env.items():
            cmd += ["-e", f"{key}={value}"]
        cmd.append(build.image)
        subprocess.run(cmd, check=True)
        return DeployResult(deploy_id=deploy_id, detail=f"http://localhost:{build.port}")

    def status(self, deploy_id: str) -> DeployStatus:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", deploy_id],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return DeployStatus(ready=False, detail="not found")
        state = result.stdout.strip()
        return DeployStatus(ready=state == "running", detail=state)

    def logs(self, deploy_id: str) -> Iterator[str]:
        result = subprocess.run(
            ["docker", "logs", deploy_id], capture_output=True, text=True, check=False
        )
        yield from (result.stdout + result.stderr).splitlines()

    def teardown(self, deploy_id: str) -> None:
        subprocess.run(["docker", "rm", "-f", deploy_id], check=False)

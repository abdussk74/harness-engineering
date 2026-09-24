"""Unit coverage for DeployTarget command construction, both monorepo
and standalone layouts.

LocalDeployTarget is also verified live against real Docker (see the
M10 commit message) — that's not re-run here for the same reason as
`harness build`'s own tests: slow, and doesn't belong in the fast test
loop. KubernetesDeployTarget needs a real cluster + registry to
exercise end to end, which PLAN.md explicitly doesn't require for v1
("buildable, even if I don't run it day one") — the Helm chart itself
is validated separately via `helm lint`/`helm template` (see the M10
commit message), and what's tested here is that this code builds the
right `docker`/`helm`/`kubectl`/`git` commands, via a mocked
subprocess.run.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from harness_cli.deploy_targets.base import AgentBuildSpec, BuildResult, DeployConfig
from harness_cli.deploy_targets.kubernetes import KubernetesDeployTarget
from harness_cli.deploy_targets.local import LocalDeployTarget
from harness_cli.project import ProjectLayout


def _monorepo_layout(tmp_path: Path) -> ProjectLayout:
    return ProjectLayout(
        mode="monorepo",
        build_context=tmp_path,
        project_dir=tmp_path / "examples" / "research-agent",
        entrypoint="agent:ResearchAgent",
    )


def _standalone_layout(tmp_path: Path) -> ProjectLayout:
    return ProjectLayout(
        mode="standalone",
        build_context=tmp_path,
        project_dir=tmp_path,
        entrypoint="agent:CodeReviewAgent",
        harness_git_url="https://github.com/abdussk74/harness-engineering.git",
        harness_git_ref="v1.0.0",
    )


def test_local_build_invokes_buildx_with_runtime_target(tmp_path: Path) -> None:
    spec = AgentBuildSpec(name="research-agent", layout=_monorepo_layout(tmp_path), port=8080)
    (tmp_path / ".harness").mkdir(exist_ok=True)
    target = LocalDeployTarget()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = target.build(spec)

    assert result.image == "research-agent:local"
    assert result.port == 8080
    cmd = mock_run.call_args[0][0]
    assert cmd[:3] == ["docker", "buildx", "build"]
    assert "--target" in cmd and cmd[cmd.index("--target") + 1] == "runtime"
    assert "--load" in cmd


def test_local_build_standalone_mode_uses_agent_dir_as_build_context(tmp_path: Path) -> None:
    spec = AgentBuildSpec(name="code-review-agent", layout=_standalone_layout(tmp_path), port=8080)
    target = LocalDeployTarget()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        target.build(spec)

    cmd = mock_run.call_args[0][0]
    assert cmd[-1] == str(tmp_path)  # build context is the agent's own dir, not a workspace root


def test_local_deploy_runs_container_with_env_vars() -> None:
    target = LocalDeployTarget()
    build = BuildResult(image="research-agent:local", port=8080)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = target.deploy(build, DeployConfig(env={"HARNESS_API_TOKEN": "s3cret"}))

    assert result.deploy_id.startswith("harness-")
    cmd = mock_run.call_args[0][0]
    assert cmd[:2] == ["docker", "run"]
    assert "-p" in cmd and cmd[cmd.index("-p") + 1] == "8080:8080"
    assert "-e" in cmd and cmd[cmd.index("-e") + 1] == "HARNESS_API_TOKEN=s3cret"


def test_kubernetes_build_pushes_multi_arch_to_the_registry(tmp_path: Path) -> None:
    spec = AgentBuildSpec(name="research-agent", layout=_monorepo_layout(tmp_path), port=8080)
    (tmp_path / ".harness").mkdir(exist_ok=True)
    target = KubernetesDeployTarget(registry="ghcr.io/example")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = target.build(spec)

    assert result.image == "ghcr.io/example/research-agent:latest"
    cmd = mock_run.call_args[0][0]
    assert "--push" in cmd
    assert "--platform" in cmd and cmd[cmd.index("--platform") + 1] == "linux/amd64,linux/arm64"
    assert target._chart_path == tmp_path / "helm" / "harness-agent"  # noqa: SLF001


def test_kubernetes_build_standalone_mode_fetches_chart_via_git_clone(tmp_path: Path) -> None:
    spec = AgentBuildSpec(name="code-review-agent", layout=_standalone_layout(tmp_path), port=8080)
    target = KubernetesDeployTarget(registry="ghcr.io/example")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        target.build(spec)

    calls = [call.args[0] for call in mock_run.call_args_list]
    clone_calls = [c for c in calls if c[:2] == ["git", "clone"]]
    assert len(clone_calls) == 1
    clone_cmd = clone_calls[0]
    assert "--branch" in clone_cmd and clone_cmd[clone_cmd.index("--branch") + 1] == "v1.0.0"
    assert "https://github.com/abdussk74/harness-engineering.git" in clone_cmd
    assert target._chart_path == (  # noqa: SLF001
        tmp_path / ".harness" / "_harness-chart-src" / "helm" / "harness-agent"
    )


def test_kubernetes_deploy_runs_helm_upgrade_install_with_image_and_env() -> None:
    target = KubernetesDeployTarget(registry="ghcr.io/example", namespace="agents")
    target._chart_path = Path("/repo/helm/harness-agent")  # noqa: SLF001 - set by build() normally
    build = BuildResult(image="ghcr.io/example/research-agent:latest", port=8080)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = target.deploy(build, DeployConfig(env={"HARNESS_API_TOKEN": "s3cret"}))

    cmd = mock_run.call_args[0][0]
    assert cmd[:4] == ["helm", "upgrade", "--install", result.deploy_id]
    assert "--set" in cmd
    assert "image.repository=ghcr.io/example/research-agent" in cmd
    assert "image.tag=latest" in cmd
    assert "env.HARNESS_API_TOKEN=s3cret" in cmd
    assert "--namespace" in cmd and cmd[cmd.index("--namespace") + 1] == "agents"


def test_kubernetes_deploy_before_build_raises() -> None:
    target = KubernetesDeployTarget(registry="ghcr.io/example")
    build = BuildResult(image="ghcr.io/example/x:latest", port=8080)

    try:
        target.deploy(build, DeployConfig())
    except AssertionError:
        pass
    else:
        raise AssertionError("expected an AssertionError when deploy() precedes build()")

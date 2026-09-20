from __future__ import annotations

from pathlib import Path

from harness_cli.codegen.compose import render_compose, render_otel_collector_config


def test_render_compose_uses_absolute_paths_not_relative_to_compose_file() -> None:
    workspace_root = Path("/repo")
    agent_dir = Path("/repo/examples/research-agent")

    content = render_compose(
        agent_name="research-agent",
        workspace_root=workspace_root,
        agent_dir=agent_dir,
        agent_dockerfile=Path("/repo/.harness/research-agent.Dockerfile"),
        otel_collector_config=Path("/repo/.harness/otel-collector-config.yaml"),
        api_token="s3cret",
    )

    assert "context: /repo\n" in content
    assert "dockerfile: /repo/.harness/research-agent.Dockerfile" in content
    assert "/repo/examples/research-agent:/app/agent_src" in content
    assert "/repo/.harness/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml" in content
    assert "HARNESS_API_TOKEN: s3cret" in content
    assert "dashboard/Dockerfile" in content


def test_render_compose_omits_token_when_not_configured() -> None:
    content = render_compose(
        agent_name="x",
        workspace_root=Path("/repo"),
        agent_dir=Path("/repo/x"),
        agent_dockerfile=Path("/repo/.harness/x.Dockerfile"),
        otel_collector_config=Path("/repo/.harness/otel-collector-config.yaml"),
    )

    assert "HARNESS_API_TOKEN" not in content


def test_render_otel_collector_config_wires_otlp_to_jaeger() -> None:
    content = render_otel_collector_config()

    assert "otlp:" in content
    assert "endpoint: jaeger:4317" in content

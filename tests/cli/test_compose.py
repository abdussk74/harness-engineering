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
    assert "HARNESS_LLM_PROVIDER" not in content
    assert "HARNESS_OLLAMA_BASE_URL" not in content


def test_render_compose_wires_ollama_provider() -> None:
    content = render_compose(
        agent_name="x",
        workspace_root=Path("/repo"),
        agent_dir=Path("/repo/x"),
        agent_dockerfile=Path("/repo/.harness/x.Dockerfile"),
        otel_collector_config=Path("/repo/.harness/otel-collector-config.yaml"),
        llm_provider="ollama",
        ollama_base_url="http://host.docker.internal:11434",
    )

    assert "HARNESS_LLM_PROVIDER: ollama" in content
    assert "HARNESS_OLLAMA_BASE_URL: http://host.docker.internal:11434" in content


def test_render_otel_collector_config_wires_otlp_to_jaeger() -> None:
    content = render_otel_collector_config()

    assert "otlp:" in content
    assert "endpoint: jaeger:4317" in content


def test_dashboard_gets_docker_internal_url_for_its_own_fetches_and_localhost_for_links() -> None:
    content = render_compose(
        agent_name="research-agent",
        workspace_root=Path("/repo"),
        agent_dir=Path("/repo/examples/research-agent"),
        agent_dockerfile=Path("/repo/.harness/research-agent.Dockerfile"),
        otel_collector_config=Path("/repo/.harness/otel-collector-config.yaml"),
        agent_port=8080,
    )

    assert "HARNESS_AGENT_INTERNAL_URL: http://agent:8080" in content
    assert "HARNESS_AGENT_PUBLIC_URL: http://localhost:8080" in content


def test_dashboard_gets_the_token_but_not_the_agents_llm_provider_settings() -> None:
    content = render_compose(
        agent_name="x",
        workspace_root=Path("/repo"),
        agent_dir=Path("/repo/x"),
        agent_dockerfile=Path("/repo/.harness/x.Dockerfile"),
        otel_collector_config=Path("/repo/.harness/otel-collector-config.yaml"),
        api_token="s3cret",
        llm_provider="ollama",
        ollama_base_url="http://host.docker.internal:11434",
    )

    dashboard_block = content.split("dashboard:")[1]
    assert "HARNESS_API_TOKEN: s3cret" in dashboard_block
    assert "HARNESS_LLM_PROVIDER" not in dashboard_block
    assert "HARNESS_OLLAMA_BASE_URL" not in dashboard_block

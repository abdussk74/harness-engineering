"""M7 conformance: cross-agent trace propagation.

Proves the core claim behind ctx.call(): a multi-agent A2A call chain
shows up as one distributed trace, with no manual span wiring by the
developer. citation-checker runs as a real local server (ctx.call()
makes a genuine outbound HTTP call over a real socket); research-agent
is exercised in-process via ASGI transport. Both share the
process-global TracerProvider (a test-only artifact of running two
"services" in one process), so what's actually verified is the
propagation mechanism itself: httpx instrumentation injects a W3C
traceparent header on the outbound call, and FastAPI instrumentation on
the receiving side parents its server span under it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from harness.llm.client import TracedChatModel
from harness.server.app import build_app_from_agent
from harness.telemetry.otel import configure_tracing

_CITATION_CHECKER_PATH = Path(__file__).parents[2] / "examples" / "citation-checker" / "agent.py"
_RESEARCH_AGENT_PATH = Path(__file__).parents[2] / "examples" / "research-agent" / "agent.py"


def _load_agent_cls(path: Path, module_name: str, class_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
async def citation_checker_url() -> AsyncIterator[str]:
    # The Agent Card bakes in its own URL at build time, and create_client()
    # connects to *that* declared URL, not the one used to fetch the card —
    # so the real port must be known before build_app_from_agent(), not
    # after uvicorn picks one.
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    citation_checker_cls = _load_agent_cls(
        _CITATION_CHECKER_PATH, "citation_checker_example", "CitationChecker"
    )
    app = build_app_from_agent(citation_checker_cls(), url=f"{url}/")

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)

    try:
        yield url
    finally:
        server.should_exit = True
        await server_task


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    configure_tracing("test-propagation")
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter


async def test_multi_agent_call_chain_shares_one_trace(
    citation_checker_url: str, span_exporter: InMemorySpanExporter
) -> None:
    os.environ["CITATION_CHECKER_URL"] = citation_checker_url
    try:
        research_agent_cls = _load_agent_cls(
            _RESEARCH_AGENT_PATH, "research_agent_propagation_example", "ResearchAgent"
        )
    finally:
        del os.environ["CITATION_CHECKER_URL"]

    fake_llm = TracedChatModel(
        provider="fake",
        model_name="fake-1",
        model=FakeListChatModel(responses=["Quantum computing summary."]),
    )
    research_app = build_app_from_agent(
        research_agent_cls(), url="http://testserver/", llm=fake_llm
    )

    transport = httpx.ASGITransport(app=research_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {
                    "metadata": {"harness_skill": "summarize_and_verify"},
                    "message": {
                        "messageId": "m1",
                        "role": "ROLE_USER",
                        "parts": [{"text": "quantum computing"}],
                    },
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert "error" not in body, body.get("error")
    task = body["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    text = task["status"]["message"]["parts"][0]["text"]
    assert "Quantum computing summary." in text
    assert "Verified 1 claim(s)" in text

    spans = span_exporter.get_finished_spans()
    trace_ids = {s.context.trace_id for s in spans if s.context is not None}
    span_names = [s.name for s in spans]
    assert len(trace_ids) == 1, f"expected one shared trace, got {len(trace_ids)}: {span_names}"

    # Both agents' FastAPI instrumentation emits one top-level "POST /"
    # span per inbound request. research-agent's is the trace root (no
    # incoming traceparent); citation-checker's is reached only via the
    # outbound ctx.call(), so its ancestry — however many a2a-sdk-internal
    # spans deep — must pass through a CLIENT span before running out.
    span_by_id = {s.context.span_id: s for s in spans if s.context is not None}
    post_spans = [s for s in spans if s.name == "POST /"]
    assert len(post_spans) == 2, f"expected 2 top-level inbound requests, got {len(post_spans)}"

    root_request = next(s for s in post_spans if s.parent is None)
    nested_request = next(s for s in post_spans if s.parent is not None)
    assert nested_request is not root_request

    ancestors: list[ReadableSpan] = []
    current: ReadableSpan | None = nested_request
    while current is not None and current.parent is not None:
        current = span_by_id.get(current.parent.span_id)
        if current is None:
            break
        ancestors.append(current)

    assert any(a.kind == trace.SpanKind.CLIENT for a in ancestors), (
        "citation-checker's inbound span has no CLIENT-kind ancestor — "
        f"ancestry was: {[a.name for a in ancestors]}"
    )

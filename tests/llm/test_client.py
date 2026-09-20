"""ctx.llm: verifies the GenAI span wrapping without needing a real API
key, using LangChain's FakeListChatModel — TracedChatModel's `_build()`
provider dispatch is untouched by this, only the span + pass-through
behavior around whatever chat model it holds."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from harness.llm.client import TracedChatModel
from harness.telemetry.otel import configure_tracing


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    configure_tracing("test-llm-client")
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter


async def test_ainvoke_returns_the_model_content(span_exporter: InMemorySpanExporter) -> None:
    fake_model = FakeListChatModel(responses=["hello from fake model"])
    chat = TracedChatModel(provider="fake", model_name="fake-1", model=fake_model)

    result = await chat.ainvoke("hi")

    assert result.content == "hello from fake model"


async def test_ainvoke_emits_a_genai_span_with_the_expected_attributes(
    span_exporter: InMemorySpanExporter,
) -> None:
    fake_model = FakeListChatModel(responses=["hello"])
    chat = TracedChatModel(provider="fake", model_name="fake-1", model=fake_model)

    await chat.ainvoke("hi")

    spans = [s for s in span_exporter.get_finished_spans() if s.name == "chat fake-1"]
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes is not None
    assert span.attributes["gen_ai.operation.name"] == "chat"
    assert span.attributes["gen_ai.provider.name"] == "fake"
    assert span.attributes["gen_ai.request.model"] == "fake-1"


async def test_underlying_model_is_built_lazily_on_first_ainvoke() -> None:
    chat = TracedChatModel(provider="anthropic", model_name="claude-sonnet-5")

    assert chat._model is None  # noqa: SLF001 - asserting the laziness contract directly

"""OTel SDK bootstrap: traces only for v1 (metrics/logs are noted as
future work in PLAN.md). Exports via OTLP only when
OTEL_EXPORTER_OTLP_ENDPOINT is set — otherwise tracing stays fully
in-process, so a plain `uv run` without a collector never attempts (and
fails) an export. `harness dev`'s compose stack sets that env var,
pointing it at the local OTel Collector.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False


def configure_tracing(service_name: str) -> None:
    """Sets up the process-wide TracerProvider and instruments httpx for
    outbound W3C trace-context propagation. Safe to call more than once
    — only the first call takes effect."""
    global _configured
    if _configured:
        return

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    if not HTTPXClientInstrumentor().is_instrumented_by_opentelemetry:
        HTTPXClientInstrumentor().instrument()

    _configured = True


def instrument_app(app: FastAPI) -> None:
    """Gives every inbound request a server span, correctly parented
    under any incoming W3C traceparent header — this is the receiving
    half of cross-agent trace propagation."""
    FastAPIInstrumentor.instrument_app(app)

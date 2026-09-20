"""GenAI OTel span helpers.

`gen_ai.*` semantic conventions are still "Development" status as of
this writing — OTel semconv is mid-migration to a dedicated
`semantic-conventions-genai` repo with no tagged release yet. Every
attribute name used here is isolated in this one module so an upstream
rename is a one-file fix, not a scattered refactor. See
docs/adr/0002-telemetry-model.md.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span

_tracer = trace.get_tracer("harness.llm")


@contextmanager
def genai_span(*, provider: str, model: str, operation: str = "chat") -> Iterator[Span]:
    with _tracer.start_as_current_span(f"{operation} {model}") as span:
        span.set_attribute("gen_ai.operation.name", operation)
        span.set_attribute("gen_ai.provider.name", provider)
        span.set_attribute("gen_ai.request.model", model)
        yield span

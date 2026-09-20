# ADR 0002: Telemetry model — OTel as the backbone, GenAI attributes isolated, LangSmith left to LangChain

## Status

Accepted (M7–M8).

## Context

The brief calls for OpenTelemetry as the vendor-neutral observability
backbone, OTel GenAI semantic conventions for LLM spans, and optional
LangSmith tracing — all with zero manual wiring from the developer.

Two upstream facts shaped the design, both confirmed by research before
building and by direct experience during M7:

- **OTel's GenAI semantic conventions are unstable.** As of the
  research done for PLAN.md, `gen_ai.*` attributes are "Development"
  status, mid-migration to a dedicated `semantic-conventions-genai`
  repo with no tagged release yet. Names and structure can still
  change upstream.
- **LangChain already traces to LangSmith natively.** `LANGSMITH_TRACING`
  / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT`, read directly from the
  process environment via LangChain's own callback system — no
  Harness-side integration code needed at all.

## Decision

**Traces only for v1** (metrics/logs are noted as future work, not
built). `harness.telemetry.otel.configure_tracing()` sets up the
process-wide `TracerProvider` and instruments `httpx` once per process;
`instrument_app()` instruments each FastAPI app individually.
OTLP export only activates when `OTEL_EXPORTER_OTLP_ENDPOINT` is set —
a plain `uv run` without a collector never attempts (and fails) an
export; `harness dev`'s compose stack sets it, pointing at the local
OTel Collector.

**GenAI attribute-setting is isolated in one module**
(`harness/telemetry/genai.py`). Every `gen_ai.*` attribute name used by
`ctx.llm` lives there and nowhere else, so an upstream semconv rename
is a one-file fix instead of a scattered refactor across the codebase.

**LangSmith gets no integration code.** The only gap was that
`HarnessConfig` only parsed `HARNESS_`-prefixed vars from `.env` into
its own fields — `LANGSMITH_*` (and provider API keys) in `.env` never
reached `os.environ`, where LangChain reads them directly.
`harness.config.load_env_file()` closes that gap by loading `.env` into
the process environment wholesale at app startup. (This function had
its own subtlety: `load_dotenv()`'s default search walks up from the
*calling library file's* location via stack inspection, not the
process's actual working directory — since it always runs from
`harness/config.py`, it needed `find_dotenv(usecwd=True)` composed
with `load_dotenv()` to search from wherever the developer actually
runs `harness dev`/`uv run`, not near the package's install location.)

## Consequences

- `ctx.llm`'s underlying LangChain client is built lazily, on first
  `ainvoke()`, not at `Context` construction — an agent whose skills
  never touch `ctx.llm` needs no API key (or running Ollama server) at
  all, and doesn't pay any GenAI/LangSmith wiring cost either.
- Cross-agent trace propagation (see ADR 0004) needed no
  GenAI-specific work — it's a property of the base OTel trace context,
  independent of the LLM layer entirely.
- A future semconv release may require revisiting `genai.py`'s
  attribute names; no other file should need to change.
- LangSmith trace URLs are not currently cross-linked into structured
  logs alongside the OTel `trace_id`, despite PLAN.md floating that as
  a nice-to-have. Deferred — LangChain's native tracing already makes
  LangSmith traces independently discoverable by project.

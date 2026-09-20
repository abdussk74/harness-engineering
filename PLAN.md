# Harness Engineering — PLAN.md

A zero-ops platform for A2A agents. This document is the proposed architecture,
build order, and open questions for review before milestone 1 starts. No code
has been written yet.

Decisions already made with you (2026-09-19):
- **Repo location**: `~/projects/harness-engineering` (this repo).
- **Package naming**: import name and CLI command stay `harness`. PyPI
  distribution name is `a2a-harness` (see §7 for why it's one package, not two).
- **v1 auth scheme**: Bearer token / static API key.
- **Local trace backend**: Jaeger.

---

## 1. Verified tech stack & versions (as of 2026-09-19)

Your brief correctly flagged that versions needed verification. Here's what's
current — sources are in the research; pin these as starting points, not gospel:

| Component | Package | Version | Notes |
|---|---|---|---|
| A2A spec | — | **v1.0.0** | Stable, Linux Foundation-governed. Agent Card path is now `/.well-known/agent-card.json` (the old `/.well-known/agent.json` gets a 308 redirect for compat). |
| A2A SDK | `a2a-sdk` | **1.1.4** | Official, Apache-2.0. Separable client/server/types — safe to wrap. Optional FastAPI/Starlette integration, optional SQL task stores (incl. SQLite). |
| OTel | `opentelemetry-{api,sdk}` | **1.44.0** | Lockstepped. |
| OTel OTLP export | `opentelemetry-exporter-otlp` | **1.44.0** | |
| OTel GenAI semconv | — | **unstable ("Development")** | Mid-migration to a new repo (`semantic-conventions-genai`) with no tagged release yet as of this research. Treat as a moving target — see §5. |
| LangSmith | `langsmith` | **0.13.0** | Canonical env vars are `LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_PROJECT`. The older `LANGCHAIN_TRACING_V2` family is soft-deprecated and unreliable under LangChain 1.0 middleware — don't use it. |
| LangGraph | `langgraph` | **1.2.11** | |
| LangChain | `langchain` | **1.4.2** | |
| FastAPI | `fastapi` | **0.141.1** | |
| uvicorn | `uvicorn` | **0.53.0** | |
| Pydantic | `pydantic` | **2.13.5** | |
| pydantic-settings | `pydantic-settings` | **2.15.0** | |
| Typer | `typer` | **0.27.2** | |
| structlog | `structlog` | **26.1.0** | |
| uv | `uv` | **0.12.17** | Docker pattern: copy the `uv` binary from `ghcr.io/astral-sh/uv`, `uv sync --no-install-project` for a cacheable deps layer, then `uv sync --frozen` for the project. |
| Jaeger | `jaegertracing/all-in-one` | **1.76.0** (v1 line) | Native OTLP ingestion on 4317/4318, no collector strictly required — but see §6 for why we keep one anyway. Jaeger v2 exists (built on the OTel Collector framework) but has less clear "use this for new projects" guidance yet — flagged as an open question. |
| Helm | — | **v4.0.0** shipped Nov 2025 | First major bump in 6 years; check v3→v4 breaking changes before writing the chart. |

---

## 2. Repo layout

A uv workspace with two top-level packages, matching your brief's naming exactly:

```
harness-engineering/
  pyproject.toml                # workspace root
  uv.lock
  harness/                      # the SDK — 90% of the value
    pyproject.toml
    src/harness/
      __init__.py                # exports: agent, skill, Context, Artifact
      decorators.py              # @agent, @skill
      context.py                 # Context object assembled per-request
      card.py                    # Agent Card generation from decorator metadata
      config.py                  # pydantic-settings AppConfig
      server/
        app.py                   # FastAPI app factory (build_app)
        jsonrpc.py                # JSON-RPC 2.0 dispatch, wraps a2a-sdk
        sse.py                   # SSE streaming for SendStreamingMessage/Subscribe
        tasks.py                 # task lifecycle state machine + store interface
        auth.py                  # Bearer/API-key middleware (pluggable AuthScheme)
      telemetry/
        otel.py                  # OTel SDK bootstrap, OTLP export config
        genai.py                 # gen_ai.* span helpers — isolated, semconv churn absorbed here
        langsmith.py             # optional LangSmith env-var wiring
        propagation.py           # W3C trace-context injection/extraction across A2A hops
      logging/
        structlog_config.py      # JSON logging, correlation-id processors
      llm/
        client.py                # ctx.llm — traced LangChain chat model wrapper
      _internal/                 # a2a-sdk adapter layer; never imported by user code
    tests/
  harness_cli/                   # control plane
    pyproject.toml
    src/harness_cli/
      main.py                    # Typer app: dev / build / deploy / doctor
      commands/
        dev.py
        build.py
        deploy.py
        doctor.py
      codegen/
        dockerfile.py            # renders the production Dockerfile template
        compose.py               # renders docker-compose.yml for `harness dev`
      deploy_targets/
        base.py                  # DeployTarget protocol
        local.py                 # docker compose target
        kubernetes.py            # k8s/Helm target
      dashboard/                 # local dev dashboard (small FastAPI+HTMX service)
    helm/harness-agent/           # generic chart consumed by the k8s DeployTarget
      Chart.yaml
      values.yaml
      templates/
    tests/
  examples/
    research-agent/               # north-star example, runnable end-to-end
    citation-checker/             # minimal second agent — see open question in §10
  tests/conformance/               # A2A spec conformance suite (cross-package)
  docs/adr/
    0001-a2a-protocol-layer.md
    0002-telemetry-model.md
    0003-container-deploy-abstraction.md
    0004-trace-propagation-across-a2a-hops.md
  .env.example
  README.md
```

---

## 3. The `@agent` / `@skill` / `Context` API

Fleshed out beyond the north-star snippet to cover streaming, multi-turn
input, and outbound calls to other agents:

```python
from harness import agent, skill, Context, Artifact

@agent(
    name="research-agent",
    description="Researches topics and returns cited summaries",
    version="1.0.0",
    # auth defaults to Bearer, reads HARNESS_API_TOKEN from env if omitted
)
class ResearchAgent:

    @skill(description="Summarize a topic with sources")
    async def summarize(self, topic: str, ctx: Context) -> str:
        ctx.log.info("starting summary", topic=topic)
        result = await ctx.llm.ainvoke(f"Summarize {topic} with sources")
        return result.content

    @skill(description="Deep research with progress updates and clarification")
    async def deep_research(self, topic: str, ctx: Context) -> str:
        await ctx.task.update(state="working", message="Searching sources...")

        if topic_is_ambiguous(topic):
            timeframe = await ctx.task.request_input("Which time range?")

        # Calling another A2A agent — trace context propagates automatically.
        citations = await ctx.call(
            "http://citation-checker:8080", "verify", claims=[...]
        )

        ctx.task.artifacts.add(Artifact(name="report.md", content=report))
        return report
```

- **Skill parameter schema**: derived from type hints via `pydantic.TypeAdapter`
  → JSON Schema, published in the Agent Card automatically. `ctx: Context` is
  recognized by parameter name/type and excluded from the public schema.
- **Return value handling**: a plain `str`/`dict` is auto-wrapped into an A2A
  Message/Artifact; an `AsyncGenerator` return is negotiated into an SSE
  stream; an explicit `Artifact` gives full control over typed output.
- **`Context` surface**:
  - `ctx.log` — structlog `BoundLogger`, pre-bound with `task_id`, `trace_id`,
    `span_id`, `agent_name`, `skill_name`.
  - `ctx.llm` — LangChain chat model, pre-instrumented with GenAI spans and
    (if configured) LangSmith tracing. Provider switch (API vs Ollama) is a
    config concern, invisible to skill code.
  - `ctx.task` — handle for the current Task: `.update()`, `.request_input()`,
    `.artifacts.add()`, `.cancel_requested`.
  - `ctx.call(url, skill, **kwargs)` — outbound A2A client call over an
    OTel-instrumented `httpx` client; this is the propagation mechanism for
    multi-agent trace chains (§5).
  - `ctx.span` — escape hatch to the live OTel span for custom attributes.
  - `ctx.config` — the agent's own typed `pydantic-settings` instance.

---

## 4. A2A compliance layer

- `harness.server.app.build_app(agent_instance, config)` wraps `a2a-sdk`'s
  request handler behind a FastAPI app implementing: `SendMessage`,
  `SendStreamingMessage`, `GetTask`, `ListTasks`, `CancelTask`,
  `SubscribeToTask`, push-notification-config CRUD (registered but not
  actively used in v1 — see open questions), `GetExtendedAgentCard`.
- Agent Card served at `GET /.well-known/agent-card.json`, with the legacy
  `/.well-known/agent.json` path aliased via 308 redirect.
- **Task store**: SQLite by default (a2a-sdk ships this backend already),
  file living in a mounted volume under `harness dev` — gives task
  persistence across hot-reloads for near-zero cost, vs. in-memory which
  loses everything on reload. In-memory remains available for tests.
- **State machine**: `submitted → working → {input-required ⇄ working,
  auth-required ⇄ working} → {completed, failed, canceled, rejected}`.
  Illegal transitions raise; the framework auto-transitions
  `submitted → working` on skill invocation and `→ completed/failed` based on
  return/exception.
- **Auth**: Bearer/API-key middleware for v1, applied to JSON-RPC + card
  endpoints. Built behind an `AuthScheme` protocol so OAuth2/mTLS are a
  follow-on implementation, not a redesign.
- The adapter module (`harness/_internal/`) is the only place `a2a_sdk.*`
  types are imported — everything public re-exports or wraps them under
  `harness.*` names, so upgrading or even replacing the underlying SDK later
  doesn't touch user-facing code.

---

## 5. Observability & trace propagation across A2A hops

**Core decision (ADR 0004)**: propagate trace context as standard **W3C Trace
Context** (`traceparent`/`tracestate` headers) over the JSON-RPC HTTP
transport. Since A2A v1 in this project targets HTTP+JSON-RPC only, this
needs no custom A2A extension — the same mechanism used for any
OTel-instrumented HTTP microservice chain applies directly:

- Server side: incoming request headers are extracted by standard OTel HTTP
  server instrumentation; the server span becomes a child of the caller's
  span, and `Context` is built from it (`ctx.log`, `ctx.span` inherit it).
- Client side: `ctx.call()` uses an `httpx` client instrumented with
  `opentelemetry-instrumentation-httpx`, which injects `traceparent`
  automatically. A developer who uses `ctx.call()` gets cross-agent trace
  propagation for free — a multi-agent chain shows up as one distributed
  trace with no manual span wiring.

**GenAI spans**: `ctx.llm` calls are wrapped with `gen_ai.*` attributes
(operation name, provider, model, token usage). Because this semconv area is
still in flux (§1), all attribute-setting logic lives in one module
(`harness/telemetry/genai.py`) so a naming change upstream is a one-file fix.

**LangSmith**: layered independently, not reimplemented. `harness` sets
`LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_PROJECT` from `.env` if
present; LangChain/LangGraph then trace to LangSmith natively via their own
callback system. Harness's only added job: cross-link the LangSmith trace URL
into the same structured log line as the OTel `trace_id`, so both systems are
navigable from one log entry.

**Export topology**: agent → OTLP → OTel Collector → Jaeger (see §6 for why
the Collector stays in the loop even though Jaeger can ingest OTLP directly).

---

## 6. Container build & DeployTarget abstraction

**Dockerfile** — one file, three targets, multi-stage:
1. `builder` — `python:3.12-slim` + `uv` binary copied from
   `ghcr.io/astral-sh/uv`; `uv sync --no-install-project` (cacheable deps
   layer) then `uv sync --frozen` (project layer).
2. `dev` (extends `builder`) — includes dev deps, runs
   `uvicorn ... --reload`; this is what `harness dev` bind-mounts source into.
3. `runtime` (final stage) — slim, non-root user (`harness`, uid 10001),
   `HEALTHCHECK` against the agent-card endpoint, `PYTHONUNBUFFERED=1`,
   exec-form entrypoint for correct `SIGTERM` handling and graceful task
   draining. This is the deploy unit — identical locally and off-laptop.

**Multi-arch**: `harness build` uses `docker buildx build`. Local dev builds
arm64 natively (no emulation). Multi-arch (`--platform linux/arm64,linux/amd64`)
is available via `--push`, intended for CI or explicit release builds — not
the inner dev loop.

**DeployTarget**:

```python
class DeployTarget(Protocol):
    def build(self, spec: AgentBuildSpec) -> BuildResult: ...
    def deploy(self, build: BuildResult, config: DeployConfig) -> DeployResult: ...
    def status(self, deploy_id: str) -> DeployStatus: ...
    def logs(self, deploy_id: str) -> Iterator[str]: ...
    def teardown(self, deploy_id: str) -> None: ...
```

- `LocalDeployTarget`: `docker compose up/down` against a generated compose
  file. This is what `harness dev` and `harness deploy --target local` both
  use (dev adds hot-reload + telemetry stack; deploy uses the `runtime` image).
- `KubernetesDeployTarget`: `buildx` multi-arch build + push, then
  `helm upgrade --install` against a generic `harness-agent` chart, values
  derived from `AgentBuildSpec`/`DeployConfig`. Buildable and CI-tested
  (against `kind`/`k3d`) even though you won't run it day one, per your brief.

**`harness dev` compose topology**:

```
agent (dev target, bind-mounted source, hot reload)
  → otel-collector (otlp receiver → exporter: otlp/jaeger)
      → jaeger (all-in-one, UI on :16686, native OTLP ingest)
dashboard (Agent Card + live task list + per-task Jaeger link)
```

On start, `harness dev` prints the Agent Card URL, dashboard URL, and Jaeger
UI URL.

---

## 7. On package naming

You picked `a2a-harness` as the PyPI distribution name. Proposal: ship it as
**one distribution** for v1 — `uv add a2a-harness` installs both `import
harness` (the SDK) and the `harness` CLI command — even though the source
tree keeps `harness/` and `harness_cli/` as separate packages internally in
the uv workspace. Splitting into `a2a-harness-sdk` / `a2a-harness-cli` is a
mechanical change we can make later if there's ever a reason for someone to
install one without the other; no reason to pay that complexity now.

---

## 8. Testing strategy

- Unit tests (`pytest` + `pytest-asyncio`) per module: decorators, Context
  assembly, Agent Card generation, task state machine transitions.
- **A2A conformance suite** (`tests/conformance/`): spins up `build_app()`
  with a trivial fixture agent and asserts — Agent Card served & schema-valid
  at the well-known path (+ legacy redirect), each JSON-RPC method responds
  per spec, illegal task-state transitions are rejected, SSE stream format is
  correct, unauthenticated requests are rejected. (I didn't find a confirmed
  official A2A Test Compatibility Kit during research — worth one more
  targeted check before milestone 11; if one exists, prefer it over a
  hand-rolled suite where it overlaps.)
- `LocalDeployTarget` tested via real `docker compose up/down` in CI.
  `KubernetesDeployTarget` tested against an ephemeral `kind`/`k3d` cluster in CI.
- The `research-agent` example doubles as an end-to-end smoke test: `harness
  dev` → curl the Agent Card → send a message via JSON-RPC → assert
  completion → assert a trace appears in Jaeger.

---

## 9. Milestones (each a runnable, tested vertical slice)

| # | Slice | Deliverable |
|---|---|---|
| M0 | Bootstrap | uv workspace, `harness_cli` skeleton with only `harness doctor` (docker/buildx/compose/uv/port checks), CI skeleton (lint+mypy+pytest) |
| M1 | Minimal A2A server | Hand-wired `a2a-sdk` server, one hardcoded skill, `SendMessage`+`GetTask`, in-memory store, Agent Card served. Curl-able; first conformance tests pass. |
| M2 | Decorators + Card gen | `@agent`/`@skill`/`Context` (log + task only) layered over M1; Agent Card now generated from decorator metadata. North-star example runs via `uv run` (LLM stubbed). |
| M3 | Task lifecycle + SSE | Full state machine incl. `input-required`/`auth-required`/`rejected`; `SendStreamingMessage`/`SubscribeToTask`; `ctx.task.update()`/`request_input()`. |
| M4 | Auth | Bearer/API-key middleware, `.env`-configured, applied across endpoints. |
| M5 | Dockerization | Multi-stage/multi-target Dockerfile, non-root, healthcheck, graceful shutdown; `harness build`. Native arm64 verified; multi-arch verified via CI. |
| M6 | `harness dev` | Full compose topology (agent + collector + jaeger + dashboard skeleton), hot reload, doctor pre-checks, printed URLs. |
| M7 | OTel + GenAI + propagation | OTel bootstrap, OTLP export, `ctx.llm` with `gen_ai.*` spans, W3C propagation via `ctx.call()`. Add `citation-checker` example agent to prove a 2-agent chain renders as one distributed trace. |
| M8 | LangSmith + Ollama | Env-var-only LangSmith enablement; `ctx.llm` provider switch to local Ollama. Same example runs fully offline, or with LangSmith traces, no agent code changes. |
| M9 | Dashboard | Agent Card view, live task list, per-task Jaeger link-outs. |
| M10 | DeployTarget: k8s/Helm | Generic chart, `harness deploy --target k8s`, CI-tested against `kind`/`k3d`. |
| M11 | Hardening | Conformance suite filled out, ADRs written, README quickstart finalized and verified against a clean clone, tag v1. |

---

## 10. Open questions

These are genuinely open — my recommendation is stated, but they're worth a
quick decision before the relevant milestone:

1. **Jaeger v1 vs v2**: v1.76 (classic all-in-one) is simpler and what most
   current tutorials target; v2 is where new Jaeger development is focused
   and is itself built on the OTel Collector framework. *Recommendation:
   start on v1.76 for M6 — revisit for a v1.x follow-up once v2's local-dev
   story is clearer.*
2. **Standalone OTel Collector container**: Jaeger now ingests OTLP natively,
   so the Collector is technically optional for v1's topology. *Recommendation:
   keep it anyway* — it's what your brief specified, and it's the seam that
   lets us fan out to a second backend (or add sampling/GenAI-attribute
   transforms) later without touching the agent. Flagging the added
   container as a conscious trade-off, not an oversight.
3. **GenAI semconv churn**: implement against the current
   "Development"-status `gen_ai.*` attributes now (isolated in one module),
   accepting a future migration when the new semconv repo cuts a release —
   or delay GenAI-specific spans until that stabilizes? *Recommendation:
   implement now* — it's core to the product's value proposition, and the
   isolation strategy in §5 caps the blast radius.
4. **Second example agent**: your brief says "one end-to-end example agent,"
   but proving cross-agent trace propagation (a real differentiator) needs
   at least two. *Recommendation: add a minimal `citation-checker` agent
   for M7*, purely as a trace-propagation demo, not a second maintained
   product surface. Flagging since it's a scope addition beyond what was
   written.
5. **Push notifications** (webhook callbacks for task updates, part of the
   A2A spec): not mentioned in your brief. *Recommendation: out of v1
   scope* — SSE streaming covers the "long-running task" need; the JSON-RPC
   methods are registered but return "not implemented" until a later pass.
6. **Signed Agent Cards**: your brief lists this among things Harness "must
   provide," but v1 scope says "one auth scheme." *Recommendation: treat as
   a documented seam only (part of the `AuthScheme`/card-signing interface),
   not built in v1* — confirm this reading is right.
7. **CI provider**: not specified. *Assuming GitHub Actions* unless you'd
   rather use something else.
8. **A2A conformance**: worth a quick check for an official Test
   Compatibility Kit before M11, rather than relying solely on a hand-rolled
   suite, if one exists and is usable standalone.

Let me know how you'd like these resolved (or tell me to just go with the
recommendations), and any corrections to the milestone order — then I'll
start on M0.

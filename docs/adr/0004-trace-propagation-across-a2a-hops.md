# ADR 0004: Trace propagation across A2A hops

## Status

Accepted (M7), verified live.

## Context

PLAN.md's stated differentiator: a multi-agent A2A call chain (agent A
calls agent B via `ctx.call()`) should show up as *one* distributed
trace, automatically, with no manual span wiring by the developer.

This needed answering a genuinely open question empirically, not just
designing around it: does OTel's span context (Python `contextvars`
under the hood) survive the several `asyncio.create_task()` boundaries
inside both `a2a-sdk`'s own request pipeline (its producer/consumer
tasks per `ActiveTask`) *and* Harness's own suspend/resume machinery
for `ctx.task.request_input()` (ADR-worthy in its own right — see the
M3 commit message for why a skill can't just `await` in place across
requests)? If context doesn't propagate through those hops, an outbound
`ctx.call()` deep inside a spawned task would start a *new* trace
instead of continuing the inbound one.

## Decision

Use standard **W3C Trace Context** (`traceparent` header) over the
JSON-RPC HTTP transport — no custom A2A extension needed, since v1
targets HTTP+JSON-RPC only (see ADR 0001). Mechanically:

- `harness.telemetry.otel.configure_tracing()` instruments `httpx`
  once per process (`HTTPXClientInstrumentor`). Any `httpx.AsyncClient`
  created afterward — including the one `a2a-sdk`'s own client
  constructs internally for `ctx.call()` — automatically injects
  `traceparent` on outbound requests. `ctx.call()`
  (`harness/_internal/outbound_call.py`) needed zero
  propagation-specific code as a result.
- `instrument_app()` instruments each agent's FastAPI app
  (`FastAPIInstrumentor`), which extracts an incoming `traceparent` and
  parents the inbound server span under it.

## Verification

Rather than trust the design, M7 built a second example agent
(`citation-checker`) purely to test this, and a live test
(`tests/conformance/test_m7_telemetry.py`) that runs citation-checker
as a real server on a real socket and research-agent over ASGI
transport, with an `InMemorySpanExporter` capturing spans from both.
Confirmed: every span across the whole call chain shares one
`trace_id`, and citation-checker's inbound span chains back through a
`CLIENT`-kind span to research-agent's outbound `ctx.call()` — Python's
`contextvars` do propagate correctly through `asyncio.create_task()`,
including through both layers of task indirection.

One correctness bug surfaced along the way and is now fixed, not just
noted: an agent's Agent Card bakes in its own URL at build time, and
`a2a-sdk`'s client connects to *that* declared URL, not whatever URL
was used to resolve the card. A placeholder port in a test caused "all
connection attempts failed" until the real port was known before
`build_app_from_agent()` ran.

A second, unrelated bug surfaced while building the dashboard's
per-task trace links (M9): tagging "whatever span is currently active"
with `harness.task_id` silently failed ("Setting attribute on ended
span") when done inside a background/resumed `execute()` call, since
the ambient span from `a2a-sdk`'s own internals may already have ended
by that point. Fixed by giving that tag its own short,
self-contained span instead of relying on ambient context — unrelated
to propagation correctness itself, but a reminder that "current span"
is not a safe assumption once background tasks are involved.

## Consequences

- Propagation is a property of instrumenting `httpx` once, not
  something `ctx.call()` has to implement or that skill authors have to
  think about.
- This only covers the JSON-RPC/HTTP transport. A future gRPC client
  transport (out of v1 scope per ADR 0001) would need its own
  instrumentation.
- The `harness.task` span (M9) exists specifically to correlate an A2A
  `task_id` with a trace, since no other natural correlation exists —
  documented here because it's a propagation-adjacent decision, not
  because it changes how propagation itself works.

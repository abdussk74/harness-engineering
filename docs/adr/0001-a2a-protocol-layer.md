# ADR 0001: A2A protocol layer — wrap `a2a-sdk`, isolate it entirely in `harness/_internal`

## Status

Accepted (M1–M3).

## Context

The core promise of this project is that a developer writes only
`@agent`/`@skill` methods and gets a spec-compliant A2A server for
free. That requires implementing (or wrapping) the full A2A v1.0
surface: Agent Card discovery, JSON-RPC 2.0 dispatch, SSE streaming,
the task lifecycle state machine, and typed artifacts.

An official Python SDK exists (`a2a-sdk`, Apache-2.0, ~4.9M weekly
downloads at time of writing) implementing all of this against the
A2A v1.0 spec, with separable client/server/types modules and optional
FastAPI/Starlette integration.

## Decision

Wrap `a2a-sdk` (pinned `>=1.1.4`) rather than hand-rolling the protocol.
Every `a2a.*` import lives under `harness/_internal/` — the executor
(`multi_skill_executor.py`), the outbound client (`outbound_call.py`),
the task controller (`task_controller.py`) — or in `harness/server/`,
which assembles the FastAPI app. No public `harness` module (`context`,
`decorators`, `card`) imports `a2a` directly. A developer using
`@agent`/`@skill`/`Context` never needs to know `a2a-sdk` exists.

Two consequences of this SDK's design shaped the executor:

- **All wire types are protobuf, not pydantic.** `a2a.types.*` is
  generated from `a2a_pb2`. Internal code builds/reads these via
  `google.protobuf.json_format` rather than pydantic models. This is
  fully contained in `_internal`; the public `Context`/`Artifact`
  surface never exposes a protobuf type.
- **No native "call skill X" RPC.** A2A's `SendMessage` is
  conversational — one message, not a tool call with a name and
  typed args. Multi-skill routing is therefore a Harness *convention*,
  not part of the base spec: an optional `metadata["harness_skill"]`
  selects the skill (required once an agent exposes more than one),
  and structured arguments travel in a `DataPart` matching the skill's
  parameter names, with single-parameter skills also accepting plain
  text as a convenience. This is documented for client authors, not
  hidden — it's the one A2A-level behavior Harness adds rather than
  wraps.

## Consequences

- Upgrading or even replacing the underlying SDK is a `harness/_internal`
  change, not a public API break — validated in practice: M7 added
  `a2a.client` usage for `ctx.call()` without touching `Context`,
  `decorators`, or any example agent.
- The multi-skill routing convention is Harness-specific and not
  portable to a generic A2A client that doesn't know about it — a
  deliberate tradeoff; the alternative (one A2A agent per skill) was
  rejected as working against the framework's "one agent, many related
  skills" mental model from the north-star example.
- v1 targets JSON-RPC over HTTP only (matching `harness dev`'s compose
  topology); gRPC transport, which `a2a-sdk` also supports, is out of
  scope.

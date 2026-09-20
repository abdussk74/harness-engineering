"""The `Context` object passed to every `@skill` method.

M2 wires `log` and a minimal `task` identity. Interactive task control
(`task.update()`, `task.request_input()`) and `llm`/`call` land in M3
and M7 respectively — the shape here is additive, not replaced.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog


@dataclass(frozen=True)
class TaskHandle:
    """Identity of the task backing the current skill invocation."""

    id: str
    context_id: str


@dataclass
class Context:
    """Per-invocation context: logging, task identity, agent/skill identity."""

    log: structlog.typing.FilteringBoundLogger
    task: TaskHandle
    agent_name: str
    skill_id: str

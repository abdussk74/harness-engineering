"""The `Context` object passed to every `@skill` method.

`task` is a `TaskController` Protocol so this module stays free of any
a2a-sdk import (only `harness._internal` is allowed to import `a2a`
directly) — the concrete implementation lives in
`harness._internal.task_controller.LiveTaskController`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import structlog


@runtime_checkable
class TaskController(Protocol):
    """Interactive control over the task backing the current skill invocation."""

    id: str
    context_id: str

    async def update(self, *, state: str = "working", message: str | None = None) -> None:
        """Publishes a task status update. `state` is one of: working,
        input-required, auth-required (terminal states are set by the
        framework automatically from the skill's return/exception)."""
        ...

    async def request_input(self, prompt: str) -> str:
        """Publishes an input-required update and waits for the caller's reply.

        Suspends the skill in place: the framework returns control to the
        A2A client (task state becomes `input-required`) while this
        coroutine parks until a follow-up message arrives for the same
        task, at which point it resumes with that message's text.
        """
        ...


@dataclass
class Context:
    """Per-invocation context: logging, task control, agent/skill identity."""

    log: structlog.typing.FilteringBoundLogger
    task: TaskController
    agent_name: str
    skill_id: str

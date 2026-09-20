"""The `Context` object passed to every `@skill` method.

`task` is a `TaskController` Protocol so this module stays free of any
a2a-sdk import (only `harness._internal` is allowed to import `a2a`
directly) — the concrete implementation lives in
`harness._internal.task_controller.LiveTaskController`. `call` is typed
structurally for the same reason — its implementation
(`harness._internal.outbound_call.call_agent`) is an a2a-sdk client
underneath. `llm` is the one exception: LangChain is the advertised
public interface (`ctx.llm.ainvoke(...).content`, straight from the
north-star example), not something Harness hides.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import structlog
from langchain_core.messages import BaseMessage


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


@runtime_checkable
class ChatModel(Protocol):
    async def ainvoke(self, prompt: str) -> BaseMessage: ...


@dataclass
class Context:
    """Per-invocation context: logging, task control, LLM, outbound
    calls, agent/skill identity."""

    log: structlog.typing.FilteringBoundLogger
    task: TaskController
    llm: ChatModel
    call: Callable[..., Awaitable[str]]
    agent_name: str
    skill_id: str

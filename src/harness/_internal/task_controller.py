"""Concrete `TaskController`: publishes lifecycle events via a2a-sdk's
`TaskUpdater` and, for `request_input`, coordinates with the executor's
per-task pause registry (see `multi_skill_executor.py` for why a plain
`await` inside the skill can't just suspend in place across requests).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState

STATE_MAP: dict[str, TaskState] = {
    "submitted": TaskState.TASK_STATE_SUBMITTED,
    "working": TaskState.TASK_STATE_WORKING,
    "input-required": TaskState.TASK_STATE_INPUT_REQUIRED,
    "auth-required": TaskState.TASK_STATE_AUTH_REQUIRED,
    "completed": TaskState.TASK_STATE_COMPLETED,
    "failed": TaskState.TASK_STATE_FAILED,
    "canceled": TaskState.TASK_STATE_CANCELED,
    "rejected": TaskState.TASK_STATE_REJECTED,
}


class LiveTaskController:
    """The real `ctx.task` implementation, bound to one skill invocation."""

    def __init__(
        self,
        *,
        id: str,
        context_id: str,
        updater: TaskUpdater,
        on_wait_for_input: Callable[[], asyncio.Future[str]],
    ) -> None:
        self.id = id
        self.context_id = context_id
        self._updater = updater
        self._on_wait_for_input = on_wait_for_input

    async def update(self, *, state: str = "working", message: str | None = None) -> None:
        agent_message = self._updater.new_agent_message([Part(text=message)]) if message else None
        await self._updater.update_status(STATE_MAP[state], message=agent_message)

    async def request_input(self, prompt: str) -> str:
        await self._updater.requires_input(self._updater.new_agent_message([Part(text=prompt)]))
        future = self._on_wait_for_input()
        return await future

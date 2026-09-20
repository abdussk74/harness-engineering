"""M1 scaffolding: a single hardcoded skill wired directly to an AgentExecutor.

`@agent`/`@skill` decorator-driven, multi-skill routing (by message
metadata) replaces `SingleSkillExecutor` in M2. The `TaskUpdater` /
`RequestContext` plumbing here is exactly what `Context` (M2) wraps.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus

SkillFn = Callable[[str], Awaitable[str]]


class SingleSkillExecutor(AgentExecutor):
    """Dispatches every incoming message to one hardcoded async skill function."""

    def __init__(self, skill_fn: SkillFn) -> None:
        self._skill_fn = skill_fn

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None

        # The executor owns creating the initial Task record; the framework
        # only appends further status/artifact update events against it.
        await event_queue.enqueue_event(
            Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            )
        )

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()

        user_input = context.get_user_input()
        try:
            result_text = await self._skill_fn(user_input)
        except Exception as exc:  # noqa: BLE001 - any skill failure becomes a failed task
            await updater.failed(updater.new_agent_message([Part(text=str(exc))]))
            return

        await updater.complete(updater.new_agent_message([Part(text=result_text)]))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

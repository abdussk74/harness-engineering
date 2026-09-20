"""Dispatches incoming A2A messages to the right `@skill` method.

A2A's base `SendMessage` RPC has no "call skill X" parameter — it's a
conversational protocol, not an RPC-per-tool one. Harness's convention
(documented for client authors, not part of the base spec): set
`metadata["harness_skill"]` to a skill id to pick it explicitly; it's
optional when the agent only exposes one skill. Structured arguments go
in a `DataPart` matching the skill's parameter names; a single-parameter
skill also accepts a plain text part as a convenience.

Multi-turn `ctx.task.request_input()` note: the a2a-sdk's AgentExecutor
contract requires `execute()` to *return* to yield control on an
input-required task — the framework's per-task producer loop can't
dequeue the follow-up message until execute() returns. So a skill body
can't literally suspend on the call stack that execute() awaits
directly. Instead, each fresh invocation runs the skill as an
independent `asyncio.Task`; execute() waits only until that task either
finishes or signals it's parked on `request_input()`, then returns
either way. The *same* ActiveTask (and its event queue) persists across
multiple execute() calls for one task_id, so the skill task keeps
running and enqueuing events after execute() has already returned. The
per-task-id `_pending` registry is what lets the *next* execute() call
find that still-running skill task and resolve its waiting future
instead of starting the skill over.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus
from google.protobuf import json_format

from harness._internal.outbound_call import call_agent
from harness._internal.task_controller import LiveTaskController
from harness.config import HarnessConfig
from harness.context import Context
from harness.decorators import AgentMeta, SkillMeta
from harness.llm.client import TracedChatModel, build_chat_model
from harness.logging.structlog_config import get_logger

SKILL_METADATA_KEY = "harness_skill"


@dataclass
class _PendingSkill:
    """One skill invocation still alive across execute() calls."""

    skill_task: asyncio.Task[None]
    waiting_event: asyncio.Event
    input_future: asyncio.Future[str] | None = None


class HarnessAgentExecutor(AgentExecutor):
    """Routes each request to one `@skill` method on a decorated agent instance."""

    def __init__(
        self,
        agent_instance: Any,
        meta: AgentMeta,
        config: HarnessConfig | None = None,
        *,
        llm: TracedChatModel | None = None,
    ) -> None:
        self._agent_instance = agent_instance
        self._meta = meta
        self._skills_by_id = {s.id: s for s in meta.skills}
        self._pending: dict[str, _PendingSkill] = {}
        config = config or HarnessConfig()
        self._llm: TracedChatModel = llm or build_chat_model(
            provider=config.llm_provider,
            model=config.llm_model,
            ollama_base_url=config.ollama_base_url,
        )

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        task_id = context.task_id

        pending = self._pending.get(task_id)
        if pending is not None:
            await self._resume(context, pending)
            return

        await self._start(context, event_queue)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        task_id = context.task_id

        pending = self._pending.pop(task_id, None)
        if pending is not None and not pending.skill_task.done():
            pending.skill_task.cancel()

        updater = TaskUpdater(event_queue, task_id, context.context_id)
        await updater.cancel()

    async def _start(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        task_id = context.task_id
        context_id = context.context_id

        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            )
        )
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()

        skill_meta = self._resolve_skill(context)
        if isinstance(skill_meta, str):
            await updater.failed(updater.new_agent_message([Part(text=skill_meta)]))
            return

        try:
            kwargs = self._resolve_kwargs(context, skill_meta)
        except ValueError as exc:
            await updater.failed(updater.new_agent_message([Part(text=str(exc))]))
            return

        log = get_logger(
            agent_name=self._meta.name,
            skill_id=skill_meta.id,
            task_id=task_id,
            context_id=context_id,
        )
        waiting_event = asyncio.Event()

        def on_wait_for_input() -> asyncio.Future[str]:
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            self._pending[task_id].input_future = future
            waiting_event.set()
            return future

        task_controller = LiveTaskController(
            id=task_id,
            context_id=context_id,
            updater=updater,
            on_wait_for_input=on_wait_for_input,
        )
        ctx = Context(
            log=log,
            task=task_controller,
            llm=self._llm,
            call=call_agent,
            agent_name=self._meta.name,
            skill_id=skill_meta.id,
        )
        method = getattr(self._agent_instance, skill_meta.method_name)

        async def run_skill() -> None:
            try:
                result = await method(**kwargs, ctx=ctx)
            except Exception as exc:  # noqa: BLE001 - any skill failure becomes a failed task
                log.error("skill failed", error=str(exc))
                await updater.failed(updater.new_agent_message([Part(text=str(exc))]))
                return
            finally:
                self._pending.pop(task_id, None)
            await updater.complete(updater.new_agent_message([Part(text=str(result))]))

        skill_task = asyncio.create_task(run_skill())
        pending = _PendingSkill(skill_task=skill_task, waiting_event=waiting_event)
        self._pending[task_id] = pending
        await self._wait_for_pause_or_completion(pending)

    async def _resume(self, context: RequestContext, pending: _PendingSkill) -> None:
        if pending.input_future is not None and not pending.input_future.done():
            pending.input_future.set_result(context.get_user_input())
        pending.waiting_event.clear()
        await self._wait_for_pause_or_completion(pending)

    @staticmethod
    async def _wait_for_pause_or_completion(pending: _PendingSkill) -> None:
        waiting_task = asyncio.create_task(pending.waiting_event.wait())
        done, still_pending = await asyncio.wait(
            {pending.skill_task, waiting_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if waiting_task in still_pending:
            waiting_task.cancel()
        if pending.skill_task in done:
            exc = pending.skill_task.exception()
            if exc is not None:
                raise exc
        # else: the skill is parked in request_input(); _pending keeps its
        # entry so the next execute() call for this task_id can resume it.

    def _resolve_skill(self, context: RequestContext) -> SkillMeta | str:
        """Returns the SkillMeta to invoke, or an error string for the caller."""
        requested_id = context.metadata.get(SKILL_METADATA_KEY)
        if requested_id:
            skill_meta = self._skills_by_id.get(requested_id)
            if skill_meta is None:
                return f"Unknown skill '{requested_id}'."
            return skill_meta
        if len(self._meta.skills) == 1:
            return self._meta.skills[0]
        return (
            "This agent has multiple skills; set metadata['harness_skill'] to one of: "
            + ", ".join(self._skills_by_id)
        )

    def _resolve_kwargs(self, context: RequestContext, skill_meta: SkillMeta) -> dict[str, Any]:
        data = self._extract_data_part(context)

        if data is not None:
            missing = [p.name for p in skill_meta.params if p.required and p.name not in data]
            if missing:
                raise ValueError(f"Missing required field(s): {', '.join(missing)}")
            return {p.name: data[p.name] for p in skill_meta.params if p.name in data}

        if not skill_meta.params:
            return {}

        if len(skill_meta.params) == 1:
            return {skill_meta.params[0].name: context.get_user_input()}

        raise ValueError(
            "This skill takes multiple parameters; send a DataPart matching: "
            + ", ".join(p.name for p in skill_meta.params)
        )

    @staticmethod
    def _extract_data_part(context: RequestContext) -> dict[str, Any] | None:
        message = context.message
        if message is None:
            return None
        for part in message.parts:
            part_dict = json_format.MessageToDict(part)
            data = part_dict.get("data")
            if isinstance(data, dict):
                return data
        return None

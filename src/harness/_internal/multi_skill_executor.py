"""Dispatches incoming A2A messages to the right `@skill` method.

A2A's base `SendMessage` RPC has no "call skill X" parameter — it's a
conversational protocol, not an RPC-per-tool one. Harness's convention
(documented for client authors, not part of the base spec): set
`metadata["harness_skill"]` to a skill id to pick it explicitly; it's
optional when the agent only exposes one skill. Structured arguments go
in a `DataPart` matching the skill's parameter names; a single-parameter
skill also accepts a plain text part as a convenience.
"""

from __future__ import annotations

from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus
from google.protobuf import json_format

from harness.context import Context, TaskHandle
from harness.decorators import AgentMeta, SkillMeta
from harness.logging.structlog_config import get_logger

SKILL_METADATA_KEY = "harness_skill"


class HarnessAgentExecutor(AgentExecutor):
    """Routes each request to one `@skill` method on a decorated agent instance."""

    def __init__(self, agent_instance: Any, meta: AgentMeta) -> None:
        self._agent_instance = agent_instance
        self._meta = meta
        self._skills_by_id = {s.id: s for s in meta.skills}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None

        await event_queue.enqueue_event(
            Task(
                id=context.task_id,
                context_id=context.context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            )
        )
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
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
            task_id=context.task_id,
            context_id=context.context_id,
        )
        ctx = Context(
            log=log,
            task=TaskHandle(id=context.task_id, context_id=context.context_id),
            agent_name=self._meta.name,
            skill_id=skill_meta.id,
        )

        method = getattr(self._agent_instance, skill_meta.method_name)
        try:
            result = await method(**kwargs, ctx=ctx)
        except Exception as exc:  # noqa: BLE001 - any skill failure becomes a failed task
            log.error("skill failed", error=str(exc))
            await updater.failed(updater.new_agent_message([Part(text=str(exc))]))
            return

        await updater.complete(updater.new_agent_message([Part(text=str(result))]))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()

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

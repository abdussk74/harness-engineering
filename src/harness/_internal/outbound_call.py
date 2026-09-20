"""ctx.call(): outbound calls to other A2A agents.

Trace context propagates automatically: once httpx is OTel-instrumented
(harness.telemetry.otel.configure_tracing does this once per process),
every httpx request — including the ones a2a-sdk's client makes under
the hood — gets a W3C `traceparent` header injected for free. This
module doesn't do anything propagation-specific itself; it just has to
not get in the way of that instrumentation.
"""

from __future__ import annotations

import uuid
from typing import Any

from a2a.client import ClientConfig, create_client
from a2a.types import SendMessageRequest, TaskState
from google.protobuf import json_format

_TERMINAL_STATES = {
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
}


async def call_agent(url: str, skill: str, **kwargs: Any) -> str:
    """Calls `skill` on the agent at `url` with `kwargs` as its
    arguments (sent as a DataPart, matching what the receiving agent's
    dispatcher expects), and returns its final response text."""
    client = await create_client(url, client_config=ClientConfig(streaming=False))
    try:
        request = SendMessageRequest()
        json_format.ParseDict(
            {
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"data": kwargs}],
                },
                "metadata": {"harness_skill": skill},
            },
            request,
        )

        async for response in client.send_message(request):
            status = None
            if response.HasField("task") and response.task.status.state in _TERMINAL_STATES:
                status = response.task.status
            elif (
                response.HasField("status_update")
                and response.status_update.status.state in _TERMINAL_STATES
            ):
                status = response.status_update.status
            if status is not None:
                return "\n".join(part.text for part in status.message.parts if part.text)
        raise RuntimeError(f"Agent at {url} never completed skill '{skill}'.")
    finally:
        await client.close()

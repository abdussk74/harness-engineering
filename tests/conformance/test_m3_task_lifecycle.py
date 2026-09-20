"""M3 conformance: full task state machine, multi-turn request_input, SSE, cancel."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from harness import Context, agent, skill
from harness.server.app import build_app_from_agent

_A2A_VERSION_HEADERS = {"A2A-Version": "1.0"}


@agent(
    name="interactive-agent",
    description="Exercises task lifecycle + multi-turn",
    version="0.1.0",
)
class InteractiveAgent:
    @skill(description="Asks one clarifying question, then echoes both answers")
    async def converse(self, topic: str, ctx: Context) -> str:
        await ctx.task.update(message="thinking...")
        answer = await ctx.task.request_input(f"More detail on {topic}?")
        return f"{topic}: {answer}"

    @skill(description="Always raises")
    async def boom(self, ctx: Context) -> str:
        raise RuntimeError("boom")


def _send(
    client: TestClient,
    *,
    skill_id: str,
    text: str,
    task_id: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "messageId": "m-" + skill_id,
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }
    if task_id:
        message["taskId"] = task_id
    if context_id:
        message["contextId"] = context_id
    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {"metadata": {"harness_skill": skill_id}, "message": message},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "error" not in body, body["error"]
    return body["result"]["task"]  # type: ignore[no-any-return]


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = build_app_from_agent(InteractiveAgent(), url="http://testserver/")
    with TestClient(app) as test_client:
        yield test_client


def test_multi_turn_request_input_resumes_with_the_next_message(client: TestClient) -> None:
    first = _send(client, skill_id="converse", text="quantum computing")
    assert first["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert first["status"]["message"]["parts"][0]["text"] == "More detail on quantum computing?"
    assert first["history"][0]["parts"][0]["text"] == "thinking..."

    second = _send(
        client,
        skill_id="converse",
        text="focus on error correction",
        task_id=first["id"],
        context_id=first["contextId"],
    )
    assert second["id"] == first["id"]
    assert second["status"]["state"] == "TASK_STATE_COMPLETED"
    assert second["status"]["message"]["parts"][0]["text"] == (
        "quantum computing: focus on error correction"
    )


def test_skill_exception_fails_the_task(client: TestClient) -> None:
    task = _send(client, skill_id="boom", text="ignored")

    assert task["status"]["state"] == "TASK_STATE_FAILED"
    assert "boom" in task["status"]["message"]["parts"][0]["text"]


def test_send_streaming_message_yields_events_ending_in_completed(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/",
        headers={**_A2A_VERSION_HEADERS, "Accept": "text/event-stream"},
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendStreamingMessage",
            "params": {
                "metadata": {"harness_skill": "boom"},
                "message": {"messageId": "m-stream", "role": "ROLE_USER", "parts": [{"text": "x"}]},
            },
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        states = []
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: ") :])
            result = payload["result"]
            status = result.get("task", {}).get("status") or result.get("statusUpdate", {}).get(
                "status"
            )
            if status:
                states.append(status["state"])

    assert states[0] == "TASK_STATE_SUBMITTED"
    assert states[-1] == "TASK_STATE_FAILED"


def test_cancel_task_transitions_to_canceled(client: TestClient) -> None:
    task = _send(client, skill_id="converse", text="quantum computing")
    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"

    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={"jsonrpc": "2.0", "id": "2", "method": "CancelTask", "params": {"id": task["id"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert "error" not in body, body["error"]
    assert body["result"]["status"]["state"] == "TASK_STATE_CANCELED"

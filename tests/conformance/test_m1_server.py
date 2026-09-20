"""M1 conformance: Agent Card discovery + SendMessage/GetTask round trip.

Uses one hardcoded echo skill; the decorator-driven multi-skill server
lands in M2 and gets its own conformance tests without touching these.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from harness.server.app import build_app

_A2A_VERSION_HEADERS = {"A2A-Version": "1.0"}


async def _echo(text: str) -> str:
    return f"echo: {text}"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = build_app(
        name="echo-agent",
        description="Echoes the input text back",
        version="0.1.0",
        url="http://testserver/",
        skill_id="echo",
        skill_name="Echo",
        skill_description="Echoes the input text back",
        skill_fn=_echo,
    )
    with TestClient(app) as test_client:
        yield test_client


def _send_message(client: TestClient, text: str) -> dict[str, Any]:
    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "ROLE_USER",
                    "parts": [{"text": text}],
                }
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "error" not in body, body["error"]
    return body["result"]["task"]  # type: ignore[no-any-return]


def test_agent_card_served_at_well_known_path(client: TestClient) -> None:
    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "echo-agent"
    assert card["skills"] == [
        {
            "id": "echo",
            "name": "Echo",
            "description": "Echoes the input text back",
        }
    ]
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


def test_send_message_completes_task_with_skill_output(client: TestClient) -> None:
    task = _send_message(client, "hello")

    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    message_parts = task["status"]["message"]["parts"]
    assert message_parts == [{"text": "echo: hello"}]


def test_get_task_returns_the_same_completed_task(client: TestClient) -> None:
    task = _send_message(client, "hello again")
    task_id = task["id"]

    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "GetTask",
            "params": {"id": task_id},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["id"] == task_id
    assert body["result"]["status"]["state"] == "TASK_STATE_COMPLETED"


def test_legacy_well_known_path_redirects_to_current_path(client: TestClient) -> None:
    response = client.get("/.well-known/agent.json", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/.well-known/agent-card.json"


def test_send_message_without_version_header_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "hello"}],
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32009

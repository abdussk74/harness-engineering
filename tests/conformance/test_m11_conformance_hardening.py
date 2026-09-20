"""M11: conformance coverage for the methods v1 doesn't implement.

Push notifications and extended agent cards are explicitly out of v1
scope (see PLAN.md open questions 5 and 6) — what matters is that
calling them fails *gracefully*, as clean JSON-RPC error responses per
the A2A spec, not with a raw crash or a malformed response. This is
a2a-sdk's own behavior (no push_config_store / no extended card
configured), locked in here as a conformance guarantee rather than
left as an unverified assumption.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from harness import Context, agent, skill
from harness.server.app import build_app_from_agent

_A2A_VERSION_HEADERS = {"A2A-Version": "1.0"}


@agent(name="minimal-agent", description="d", version="0.1.0")
class MinimalAgent:
    @skill(description="d")
    async def echo(self, text: str, ctx: Context) -> str:
        return text


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = build_app_from_agent(MinimalAgent(), url="http://testserver/")
    with TestClient(app) as test_client:
        yield test_client


def test_push_notifications_are_rejected_gracefully_not_supported(client: TestClient) -> None:
    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "CreateTaskPushNotificationConfig",
            "params": {"id": "x", "taskId": "nonexistent", "url": "http://example.com"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32003
    assert "not supported" in body["error"]["message"].lower()


def test_agent_card_declares_push_notifications_unsupported(client: TestClient) -> None:
    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    # Proto3 JSON omits boolean fields at their default (false) value, so
    # absence here is the correct positive assertion, not a gap.
    assert response.json()["capabilities"].get("pushNotifications", False) is False


def test_get_extended_agent_card_is_rejected_gracefully(client: TestClient) -> None:
    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={"jsonrpc": "2.0", "id": "1", "method": "GetExtendedAgentCard", "params": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32004


def test_unknown_jsonrpc_method_returns_method_not_found(client: TestClient) -> None:
    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={"jsonrpc": "2.0", "id": "1", "method": "NotARealMethod", "params": {}},
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32601


def test_get_task_for_unknown_task_id_returns_task_not_found(client: TestClient) -> None:
    response = client.post(
        "/",
        headers=_A2A_VERSION_HEADERS,
        json={"jsonrpc": "2.0", "id": "1", "method": "GetTask", "params": {"id": "does-not-exist"}},
    )

    assert response.status_code == 200
    assert "error" in response.json()

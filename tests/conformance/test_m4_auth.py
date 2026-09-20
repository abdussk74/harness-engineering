"""M4 conformance: Bearer token auth, applied uniformly across routes."""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from harness import Context, agent, skill
from harness.config import HarnessConfig
from harness.server.app import build_app_from_agent

_TOKEN = "s3cret-token"


@agent(name="guarded-agent", description="Requires a bearer token", version="0.1.0")
class GuardedAgent:
    @skill(description="Echoes the input text back")
    async def echo(self, text: str, ctx: Context) -> str:
        return f"echo: {text}"


def _send_message_json() -> dict[str, Any]:
    return {
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
    }


def test_no_auth_applied_when_token_not_configured() -> None:
    app = build_app_from_agent(GuardedAgent(), url="http://testserver/", config=HarnessConfig())

    with TestClient(app) as client:
        card = client.get("/.well-known/agent-card.json")
        send = client.post("/", headers={"A2A-Version": "1.0"}, json=_send_message_json())

    assert card.status_code == 200
    assert send.status_code == 200
    assert "error" not in send.json()


def test_agent_card_requires_bearer_token_when_configured() -> None:
    app = build_app_from_agent(
        GuardedAgent(), url="http://testserver/", config=HarnessConfig(api_token=_TOKEN)
    )

    with TestClient(app) as client:
        unauthenticated = client.get("/.well-known/agent-card.json")
        authenticated = client.get(
            "/.well-known/agent-card.json",
            headers={"Authorization": f"Bearer {_TOKEN}"},
        )

    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"] == "Bearer"
    assert authenticated.status_code == 200


def test_send_message_requires_bearer_token_when_configured() -> None:
    app = build_app_from_agent(
        GuardedAgent(), url="http://testserver/", config=HarnessConfig(api_token=_TOKEN)
    )

    with TestClient(app) as client:
        no_header = client.post("/", headers={"A2A-Version": "1.0"}, json=_send_message_json())
        wrong_token = client.post(
            "/",
            headers={"A2A-Version": "1.0", "Authorization": "Bearer wrong"},
            json=_send_message_json(),
        )
        correct_token = client.post(
            "/",
            headers={"A2A-Version": "1.0", "Authorization": f"Bearer {_TOKEN}"},
            json=_send_message_json(),
        )

    assert no_header.status_code == 401
    assert wrong_token.status_code == 401
    assert correct_token.status_code == 200
    assert "error" not in correct_token.json()

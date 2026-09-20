"""Runs the north-star example agent from PLAN.md end-to-end."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from harness.server.app import build_app_from_agent

_AGENT_PATH = Path(__file__).parents[2] / "examples" / "research-agent" / "agent.py"


def _load_research_agent_cls() -> Any:
    spec = importlib.util.spec_from_file_location("research_agent_example", _AGENT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ResearchAgent


@pytest.fixture
def client() -> Iterator[TestClient]:
    research_agent_cls = _load_research_agent_cls()
    app = build_app_from_agent(research_agent_cls(), url="http://testserver/")
    with TestClient(app) as test_client:
        yield test_client


def test_agent_card_reflects_decorator_metadata(client: TestClient) -> None:
    response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "research-agent"
    assert card["skills"] == [
        {
            "id": "summarize",
            "name": "summarize",
            "description": "Summarize a topic with sources",
        }
    ]


def test_send_message_with_single_param_uses_plain_text(client: TestClient) -> None:
    response = client.post(
        "/",
        headers={"A2A-Version": "1.0"},
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "quantum computing"}],
                }
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "error" not in body, body.get("error")
    task = body["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    text = task["status"]["message"]["parts"][0]["text"]
    assert "quantum computing" in text

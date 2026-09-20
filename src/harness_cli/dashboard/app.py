"""Live dashboard: Agent Card, live task list, per-task Jaeger links.

Polls the agent's own ListTasks JSON-RPC method on each page load
rather than maintaining separate state — the agent's task store is
already the source of truth. Plain HTML with a meta-refresh, no JS
framework: this is a dev-loop tool, not a production UI.

Per-task trace links work by tag search rather than a direct trace_id,
since there's no other natural correlation between an A2A task_id and
an OTel trace_id — see the harness.task span in
harness._internal.multi_skill_executor.

Two different agent URLs are needed, not one: this server's own httpx
calls (ListTasks, the card fetch) run inside the compose network, where
the agent is reachable at its service name; the HTML this page returns
is opened in the *user's* browser, outside that network, where the
agent is only reachable via its published host port.
"""

from __future__ import annotations

import html
import json
import os
import urllib.parse
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Harness Dashboard")

_AGENT_INTERNAL_URL = os.environ.get("HARNESS_AGENT_INTERNAL_URL", "http://localhost:8080").rstrip(
    "/"
)
_AGENT_PUBLIC_URL = os.environ.get("HARNESS_AGENT_PUBLIC_URL", "http://localhost:8080").rstrip("/")
_JAEGER_URL = os.environ.get("HARNESS_JAEGER_URL", "http://localhost:16686").rstrip("/")
_API_TOKEN = os.environ.get("HARNESS_API_TOKEN")


def _agent_headers() -> dict[str, str]:
    headers = {"A2A-Version": "1.0"}
    if _API_TOKEN:
        headers["Authorization"] = f"Bearer {_API_TOKEN}"
    return headers


async def _fetch_agent_card() -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            response = await client.get(
                f"{_AGENT_INTERNAL_URL}/.well-known/agent-card.json", headers=_agent_headers()
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        card: dict[str, Any] = response.json()
        return card


async def _fetch_tasks() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            response = await client.post(
                f"{_AGENT_INTERNAL_URL}/",
                headers={**_agent_headers(), "Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": "dashboard", "method": "ListTasks", "params": {}},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return []
        body: dict[str, Any] = response.json()
        tasks: list[dict[str, Any]] = body.get("result", {}).get("tasks", [])
        return tasks


def _jaeger_task_link(service_name: str, task_id: str) -> str:
    tags = json.dumps({"harness.task_id": task_id})
    query = urllib.parse.urlencode({"service": service_name, "tags": tags})
    return f"{_JAEGER_URL}/search?{query}"


def _task_row(task: dict[str, Any], service_name: str) -> str:
    task_id = task.get("id", "")
    state = task.get("status", {}).get("state", "UNKNOWN")
    message_parts = task.get("status", {}).get("message", {}).get("parts", [])
    preview = " ".join(p.get("text", "") for p in message_parts if p.get("text"))
    trace_link = _jaeger_task_link(service_name, task_id)
    state_class = html.escape(state.lower())
    return f"""<tr>
<td><code>{html.escape(task_id[:8])}</code></td>
<td><span class="state state-{state_class}">{html.escape(state)}</span></td>
<td>{html.escape(preview[:120])}</td>
<td><a href="{trace_link}" target="_blank" rel="noopener">trace</a></td>
</tr>"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    card = await _fetch_agent_card()
    tasks = await _fetch_tasks()
    service_name = card["name"] if card else "agent"

    if card:
        skills = ", ".join(html.escape(s["id"]) for s in card.get("skills", []))
        name = html.escape(card["name"])
        version = html.escape(card.get("version", ""))
        description = html.escape(card.get("description", ""))
        card_url = f"{_AGENT_PUBLIC_URL}/.well-known/agent-card.json"
        card_section = f"""<h2>{name} <small>v{version}</small></h2>
<p>{description}</p>
<p><strong>Skills:</strong> {skills or "(none)"}</p>
<p><a href="{card_url}" target="_blank" rel="noopener">Agent Card JSON</a></p>"""
    else:
        card_section = "<p><em>Agent not reachable yet — is it still starting up?</em></p>"

    rows = "\n".join(_task_row(t, service_name) for t in tasks) or (
        '<tr><td colspan="4"><em>No tasks yet — send this agent a message.</em></td></tr>'
    )

    return f"""<!doctype html>
<html>
<head>
<title>Harness Dashboard</title>
<meta http-equiv="refresh" content="5">
<style>
  body {{
    font-family: system-ui; max-width: 900px; margin: 2rem auto;
    padding: 0 1rem; color: #222;
  }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; }}
  code {{ font-size: 0.9em; }}
  .state {{ padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 0.85em; }}
  .state-task_state_completed {{ background: #d4edda; }}
  .state-task_state_failed,
  .state-task_state_rejected,
  .state-task_state_canceled {{ background: #f8d7da; }}
  .state-task_state_working,
  .state-task_state_submitted {{ background: #fff3cd; }}
  .state-task_state_input_required,
  .state-task_state_auth_required {{ background: #cce5ff; }}
</style>
</head>
<body>
<h1>Harness Dashboard</h1>
{card_section}
<h3>Tasks <small>(auto-refreshes every 5s)</small></h3>
<table>
<thead><tr><th>ID</th><th>State</th><th>Last message</th><th>Trace</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<p><a href="{_JAEGER_URL}" target="_blank" rel="noopener">Open Jaeger</a></p>
</body>
</html>"""


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}

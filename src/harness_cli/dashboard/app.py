"""M6 dashboard skeleton: links out to the Agent Card and Jaeger.

M9 replaces the body of `index()` with a live task list and per-task
trace links; the route shape and env-var contract here are meant to
stay stable across that change.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Harness Dashboard")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    agent_card_url = os.environ.get("HARNESS_AGENT_CARD_URL", "#")
    jaeger_url = os.environ.get("HARNESS_JAEGER_URL", "#")
    return f"""<!doctype html>
<html>
<head><title>Harness Dashboard</title></head>
<body style="font-family: system-ui; max-width: 640px; margin: 4rem auto; padding: 0 1rem;">
<h1>Harness Dashboard</h1>
<p>Live task list and per-task trace links land in M9. For now:</p>
<ul>
<li><a href="{agent_card_url}">Agent Card</a></li>
<li><a href="{jaeger_url}">Jaeger traces</a></li>
</ul>
</body>
</html>"""


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}

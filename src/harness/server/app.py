"""Builds a spec-compliant A2A JSON-RPC server as a FastAPI app.

`build_app` (M1) wires one hardcoded skill directly and stays useful for
low-level tests. `build_app_from_agent` (M2) is the real entry point:
given a `@agent`-decorated instance, it derives the Agent Card and
request routing from decorator metadata. Later milestones add: full task
lifecycle + SSE (M3), auth middleware (M4).
"""

from __future__ import annotations

from typing import Any

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from harness._internal.executor import SingleSkillExecutor, SkillFn
from harness._internal.multi_skill_executor import HarnessAgentExecutor
from harness.card import agent_card_from_meta, build_agent_card
from harness.config import HarnessConfig
from harness.decorators import agent_meta
from harness.llm.client import TracedChatModel
from harness.logging.structlog_config import configure_logging
from harness.server.auth import AuthMiddleware, BearerTokenAuth
from harness.telemetry.otel import configure_tracing, instrument_app

_LEGACY_AGENT_CARD_PATH = "/.well-known/agent.json"


def _assemble_app(
    *, agent_card: AgentCard, executor: Any, title: str, description: str, version: str
) -> FastAPI:
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        agent_card=agent_card,
    )

    app = FastAPI(title=title, description=description, version=version)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(agent_card),
        jsonrpc_routes=create_jsonrpc_routes(request_handler, rpc_url="/"),
    )

    @app.get(_LEGACY_AGENT_CARD_PATH, include_in_schema=False)
    async def _legacy_agent_card_redirect() -> RedirectResponse:
        return RedirectResponse(url=AGENT_CARD_WELL_KNOWN_PATH, status_code=308)

    @app.get("/healthz", include_in_schema=False)
    async def _healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def build_app(
    *,
    name: str,
    description: str,
    version: str,
    url: str,
    skill_id: str,
    skill_name: str,
    skill_description: str,
    skill_fn: SkillFn,
) -> FastAPI:
    """Assembles a FastAPI app implementing the A2A protocol for one hardcoded skill."""
    agent_card = build_agent_card(
        name=name,
        description=description,
        version=version,
        url=url,
        skills=[AgentSkill(id=skill_id, name=skill_name, description=skill_description)],
    )
    executor = SingleSkillExecutor(skill_fn)
    return _assemble_app(
        agent_card=agent_card,
        executor=executor,
        title=name,
        description=description,
        version=version,
    )


def build_app_from_agent(
    agent_instance: Any,
    *,
    url: str,
    config: HarnessConfig | None = None,
    llm: TracedChatModel | None = None,
) -> FastAPI:
    """Assembles a FastAPI app for a `@agent`-decorated instance.

    Raises TypeError if `agent_instance`'s class was never decorated
    with `@agent` (i.e. has no skills registered). Every route — JSON-RPC
    and Agent Card alike — requires `config.api_token` as a Bearer token
    when one is configured; unset means no auth (fine for pure-localhost
    dev, but `harness dev` should set one). `llm` overrides `ctx.llm`'s
    chat model — a test seam; production wiring builds it from `config`.
    """
    meta = agent_meta(agent_instance)
    if meta is None:
        raise TypeError(f"{type(agent_instance).__name__} is not decorated with @agent.")
    if config is None:
        config = HarnessConfig()

    configure_logging()
    configure_tracing(meta.name)
    agent_card = agent_card_from_meta(meta, url=url, streaming=True)
    executor = HarnessAgentExecutor(agent_instance, meta, config, llm=llm)
    app = _assemble_app(
        agent_card=agent_card,
        executor=executor,
        title=meta.name,
        description=meta.description,
        version=meta.version,
    )
    if config.api_token:
        app.add_middleware(AuthMiddleware, scheme=BearerTokenAuth(config.api_token))
    instrument_app(app)
    return app

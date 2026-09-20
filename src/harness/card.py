"""Agent Card construction.

M1: built from explicit fields, one hardcoded skill. M2 replaces the
call site with generation driven by ``@agent``/``@skill`` decorator
metadata — this module's shape doesn't change, only what populates it.
"""

from __future__ import annotations

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from a2a.utils.constants import TransportProtocol

from harness.decorators import AgentMeta


def agent_card_from_meta(meta: AgentMeta, *, url: str, streaming: bool = False) -> AgentCard:
    """Builds an Agent Card from `@agent`/`@skill` decorator metadata."""
    skills = [
        AgentSkill(
            id=skill_meta.id,
            name=skill_meta.id,
            description=skill_meta.description,
            tags=list(skill_meta.tags),
            examples=list(skill_meta.examples),
        )
        for skill_meta in meta.skills
    ]
    return build_agent_card(
        name=meta.name,
        description=meta.description,
        version=meta.version,
        url=url,
        skills=skills,
        streaming=streaming,
    )


def build_agent_card(
    *,
    name: str,
    description: str,
    version: str,
    url: str,
    skills: list[AgentSkill],
    streaming: bool = False,
) -> AgentCard:
    """Assembles an A2A Agent Card for a single JSON-RPC interface."""
    return AgentCard(
        name=name,
        description=description,
        version=version,
        supported_interfaces=[
            AgentInterface(
                url=url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version="1.0",
            )
        ],
        capabilities=AgentCapabilities(streaming=streaming),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=skills,
    )

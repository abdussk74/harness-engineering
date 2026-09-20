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

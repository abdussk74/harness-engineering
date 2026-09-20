"""A minimal second agent, existing purely to prove that a multi-agent
A2A call chain renders as one distributed trace (see
docs/adr/0004-trace-propagation-across-a2a-hops.md) — not a maintained
product surface the way research-agent is.
"""

from __future__ import annotations

from harness import Context, agent, skill


@agent(
    name="citation-checker",
    description="Verifies claims against sources",
    version="1.0.0",
)
class CitationChecker:
    @skill(description="Verify a list of claims")
    async def verify(self, claims: list[str], ctx: Context) -> str:
        ctx.log.info("verifying claims", count=len(claims))
        return f"Verified {len(claims)} claim(s): all plausible (stub — real checks land later)"

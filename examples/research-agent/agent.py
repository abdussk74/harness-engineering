"""The north-star example from PLAN.md.

`ctx.llm` lands in M7 — until then, `summarize` returns a canned
response so this agent is runnable and testable at every milestone.
"""

from __future__ import annotations

from harness import Context, agent, skill


@agent(
    name="research-agent",
    description="Researches topics and returns cited summaries",
    version="1.0.0",
)
class ResearchAgent:
    @skill(description="Summarize a topic with sources")
    async def summarize(self, topic: str, ctx: Context) -> str:
        ctx.log.info("starting summary", topic=topic)
        return f"Summary of {topic}: (stub summary — ctx.llm lands in M7)"

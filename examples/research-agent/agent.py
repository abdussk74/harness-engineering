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

    @skill(description="Deep research with progress updates and clarification")
    async def deep_research(self, topic: str, ctx: Context) -> str:
        ctx.log.info("starting deep research", topic=topic)
        await ctx.task.update(message="Searching sources...")
        timeframe = await ctx.task.request_input("Which time range should I focus on?")
        return f"Deep research on {topic} ({timeframe}): (stub — ctx.llm lands in M7)"

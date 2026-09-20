"""The north-star example from PLAN.md.

`summarize` stays a stub — it has no external dependencies, so it's the
fast, credential-free smoke test every milestone's tests run against.
`summarize_and_verify` is the real thing: ctx.llm for the summary,
ctx.call() to a second agent (citation-checker) to verify it. That
second hop is also what proves cross-agent trace propagation — see
docs/adr/0004-trace-propagation-across-a2a-hops.md and
tests/conformance/test_m7_telemetry.py.
"""

from __future__ import annotations

import os

from harness import Context, agent, skill

CITATION_CHECKER_URL = os.environ.get("CITATION_CHECKER_URL", "http://localhost:8081")


@agent(
    name="research-agent",
    description="Researches topics and returns cited summaries",
    version="1.0.0",
)
class ResearchAgent:
    @skill(description="Summarize a topic with sources")
    async def summarize(self, topic: str, ctx: Context) -> str:
        ctx.log.info("starting summary", topic=topic)
        return f"Summary of {topic}: (stub summary)"

    @skill(description="Summarize a topic with an LLM, then verify it via citation-checker")
    async def summarize_and_verify(self, topic: str, ctx: Context) -> str:
        ctx.log.info("starting llm summary", topic=topic)
        result = await ctx.llm.ainvoke(f"Summarize {topic} with sources")
        verification = await ctx.call(CITATION_CHECKER_URL, "verify", claims=[str(result.content)])
        return f"{result.content}\n\n{verification}"

    @skill(description="Deep research with progress updates and clarification")
    async def deep_research(self, topic: str, ctx: Context) -> str:
        ctx.log.info("starting deep research", topic=topic)
        await ctx.task.update(message="Searching sources...")
        timeframe = await ctx.task.request_input("Which time range should I focus on?")
        return f"Deep research on {topic} ({timeframe}): (stub)"

# Harness Engineering

A zero-ops platform for A2A agents. Write only your agent's business logic —
`@agent`/`@skill` decorators and a `Context` object — and get a fully
operational, [A2A-protocol](https://a2a-protocol.org)-compliant agent:
Agent Card generation, JSON-RPC + SSE, the task lifecycle, distributed
tracing, structured logging, auth, and a production Docker image, all
handled invisibly.

```python
from harness import agent, skill, Context

@agent(
    name="research-agent",
    description="Researches topics and returns cited summaries",
    version="1.0.0",
)
class ResearchAgent:
    @skill(description="Summarize a topic with sources")
    async def summarize(self, topic: str, ctx: Context) -> str:
        ctx.log.info("starting summary", topic=topic)
        result = await ctx.llm.ainvoke(f"Summarize {topic} with sources")
        return result.content
```

`harness dev` runs it locally in Docker as a spec-compliant A2A server —
hot reload, plus a local OpenTelemetry Collector, Jaeger, and dashboard
alongside it. `harness build`/`harness deploy` ship the same image
elsewhere. The developer never writes an Agent Card, a JSON-RPC handler,
an OTel span, or a Dockerfile.

## Quickstart

Requires [Docker](https://docs.docker.com/get-docker/) (Docker Desktop
or Colima) and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/abdussk74/harness-engineering.git
cd harness-engineering
uv sync
uv run harness doctor          # checks docker/buildx/compose/uv/ports

cd examples/research-agent
uv run --project ../.. harness dev
```

That prints three URLs:

- **Agent Card** — `http://localhost:8080/.well-known/agent-card.json`
- **Dashboard** — `http://localhost:3400` (live task list, per-task Jaeger links)
- **Jaeger** — `http://localhost:16686` (distributed traces)

Send it a message:

```sh
curl -X POST http://localhost:8080/ \
  -H 'Content-Type: application/json' -H 'A2A-Version: 1.0' \
  -d '{
    "jsonrpc": "2.0", "id": "1", "method": "SendMessage",
    "params": {
      "metadata": {"harness_skill": "summarize"},
      "message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": "quantum computing"}]}
    }
  }'
```

`summarize` is a stub (no LLM call, no API key needed) — good for a
first smoke test; watch it appear in the dashboard and in Jaeger.
`summarize_and_verify` uses `ctx.llm` for real and calls a second agent
(`citation-checker`) via `ctx.call()`, so the whole chain shows up as
one trace. Run it with `ANTHROPIC_API_KEY` set (copy `.env.example` to
`.env`), or develop entirely offline with `harness dev --llm-provider
ollama` if you have [Ollama](https://ollama.com) running locally.

## Writing your own agent

An agent needs two files:

```
my-agent/
  agent.py          # @agent / @skill classes
  pyproject.toml     # [tool.harness]\n entrypoint = "agent:MyAgent"
```

See [`examples/research-agent/`](examples/research-agent/) and
[`examples/citation-checker/`](examples/citation-checker/) for working
examples — including a multi-turn skill (`ctx.task.request_input()`)
and a cross-agent call (`ctx.call()`).

## CLI

| Command | What it does |
|---|---|
| `harness doctor` | Checks Docker/buildx/compose/uv and required ports |
| `harness dev` | Runs the agent locally with hot reload + OTel Collector + Jaeger + dashboard |
| `harness build --tag <image>` | Builds the production Docker image |
| `harness deploy --target local\|k8s` | Deploys the built image (docker run, or Helm) |

## Architecture

[PLAN.md](./PLAN.md) has the full architecture and milestone-by-milestone
build order. [`docs/adr/`](./docs/adr/) has the load-bearing design
decisions: the A2A protocol layer, the telemetry model, the
container/deploy abstraction, and trace propagation across A2A hops.

## Development

```sh
uv sync
uv run ruff check .
uv run ruff format .
uv run mypy src tests
uv run pytest
```

# Harness Engineering

A zero-ops platform for A2A agents. Write your agent's business logic; the
Harness handles A2A protocol compliance, deployment, tracing, and structured
logging.

**Status**: early build-out, following [PLAN.md](./PLAN.md). Milestone M0
(bootstrap) is in progress — the 5-minute quickstart below doesn't exist yet.

## Development

```sh
uv sync
uv run harness doctor
uv run pytest
```

See [PLAN.md](./PLAN.md) for the architecture, milestone order, and open
questions.

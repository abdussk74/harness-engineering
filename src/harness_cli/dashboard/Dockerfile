# syntax=docker/dockerfile:1
# The dashboard is part of the Harness control plane itself, not
# per-agent generated output, so unlike the agent's Dockerfile this one
# is hand-written and static — build context is the workspace root.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_MANAGED_PYTHON=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
EXPOSE 3000
CMD ["uvicorn", "harness_cli.dashboard.app:app", "--host", "0.0.0.0", "--port", "3000"]

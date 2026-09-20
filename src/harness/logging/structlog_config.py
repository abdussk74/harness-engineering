"""Structlog bootstrap.

JSON output by default (machine-consumable, matches the built image);
console output when stdout is a TTY, matching `harness dev`'s interactive
loop. Trace/span-id binding is added in M7 once OTel is wired in — this
module only handles the log-record shape and the fields available by M2
(task_id, context_id, agent_name, skill_id).
"""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog

_configured = False


def configure_logging(*, json_output: bool | None = None) -> None:
    """Configures structlog process-wide. Safe to call more than once."""
    global _configured
    if json_output is None:
        json_output = not sys.stdout.isatty()

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(**initial_bindings: object) -> structlog.typing.FilteringBoundLogger:
    """Returns a logger pre-bound with correlation fields for one invocation."""
    if not _configured:
        configure_logging()
    logger = structlog.get_logger().bind(**initial_bindings)
    return cast("structlog.typing.FilteringBoundLogger", logger)

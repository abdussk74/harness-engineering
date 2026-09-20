"""Container/CLI entrypoint: resolves `HARNESS_ENTRYPOINT` and serves it.

This is what the Dockerfile's CMD runs via
`uvicorn harness._internal.runtime:build_asgi_app --factory`. Not part
of the public SDK surface — developers never import this directly.
"""

from __future__ import annotations

import importlib
import os

from fastapi import FastAPI

from harness.server.app import build_app_from_agent


def _resolve_entrypoint(entrypoint: str) -> object:
    module_name, _, class_name = entrypoint.partition(":")
    if not module_name or not class_name:
        raise ValueError(f"Invalid HARNESS_ENTRYPOINT '{entrypoint}'; expected 'module:ClassName'.")
    module = importlib.import_module(module_name)
    agent_cls = getattr(module, class_name)
    return agent_cls()


def build_asgi_app() -> FastAPI:
    entrypoint = os.environ.get("HARNESS_ENTRYPOINT")
    if not entrypoint:
        raise RuntimeError("HARNESS_ENTRYPOINT is not set.")
    port = os.environ.get("HARNESS_PORT", "8080")
    agent_instance = _resolve_entrypoint(entrypoint)
    return build_app_from_agent(agent_instance, url=f"http://0.0.0.0:{port}/")

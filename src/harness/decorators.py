"""`@agent` / `@skill` — the entire public surface a developer touches.

`@skill` records parameter and metadata info on the function object;
`@agent` walks the decorated class once (at import time, not per-request)
and assembles it into `AgentMeta`, which both Agent Card generation
(`harness.card`) and request dispatch (`harness._internal.executor`)
read from. Neither decorator changes how the method is called directly —
dispatch is the executor's job.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, get_type_hints

from harness.context import Context

_F = TypeVar("_F", bound=Callable[..., Any])
_C = TypeVar("_C", bound=type)

_SKILL_ATTR = "__harness_skill__"
_AGENT_ATTR = "__harness_agent__"


@dataclass(frozen=True)
class SkillParam:
    name: str
    annotation: Any
    required: bool


@dataclass(frozen=True)
class SkillMeta:
    id: str
    description: str
    method_name: str
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    params: tuple[SkillParam, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentMeta:
    name: str
    description: str
    version: str
    skills: tuple[SkillMeta, ...] = field(default_factory=tuple)


def skill(
    *,
    description: str,
    id: str | None = None,
    tags: list[str] | None = None,
    examples: list[str] | None = None,
) -> Callable[[_F], _F]:
    """Marks a method as an A2A skill, discoverable once its class is `@agent`-decorated."""

    def decorator(func: _F) -> _F:
        sig = inspect.signature(func)
        hints = get_type_hints(func)
        params: list[SkillParam] = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            annotation = hints.get(param_name, Any)
            if annotation is Context:
                continue
            params.append(
                SkillParam(
                    name=param_name,
                    annotation=annotation,
                    required=param.default is inspect.Parameter.empty,
                )
            )
        meta = SkillMeta(
            id=id or func.__name__,
            description=description,
            method_name=func.__name__,
            tags=tuple(tags or ()),
            examples=tuple(examples or ()),
            params=tuple(params),
        )
        setattr(func, _SKILL_ATTR, meta)
        return func

    return decorator


def agent(*, name: str, description: str, version: str) -> Callable[[_C], _C]:
    """Marks a class as an A2A agent and collects its `@skill` methods."""

    def decorator(cls: _C) -> _C:
        skills = tuple(
            getattr(member, _SKILL_ATTR)
            for member in vars(cls).values()
            if callable(member) and hasattr(member, _SKILL_ATTR)
        )
        setattr(
            cls,
            _AGENT_ATTR,
            AgentMeta(name=name, description=description, version=version, skills=skills),
        )
        return cls

    return decorator


def agent_meta(agent_instance_or_cls: Any) -> AgentMeta | None:
    """Reads the `AgentMeta` attached by `@agent`, or None if undecorated."""
    cls = agent_instance_or_cls
    if not isinstance(cls, type):
        cls = type(cls)
    return getattr(cls, _AGENT_ATTR, None)

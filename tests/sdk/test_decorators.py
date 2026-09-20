from __future__ import annotations

from harness import Context, agent, skill
from harness.decorators import agent_meta


def test_agent_meta_is_none_for_undecorated_class() -> None:
    class Plain:
        pass

    assert agent_meta(Plain()) is None


def test_agent_decorator_collects_skills_in_declaration_order() -> None:
    @agent(name="multi", description="multi-skill agent", version="0.1.0")
    class MultiSkillAgent:
        @skill(description="first")
        async def alpha(self, x: str, ctx: Context) -> str:
            return x

        @skill(description="second", id="beta-id", tags=["b"], examples=["do beta"])
        async def beta(self, ctx: Context) -> str:
            return "beta"

    meta = agent_meta(MultiSkillAgent())
    assert meta is not None
    assert meta.name == "multi"
    assert [s.id for s in meta.skills] == ["alpha", "beta-id"]

    alpha, beta = meta.skills
    assert alpha.method_name == "alpha"
    assert [p.name for p in alpha.params] == ["x"]
    assert alpha.params[0].required is True

    assert beta.tags == ("b",)
    assert beta.examples == ("do beta",)
    assert beta.params == ()


def test_skill_excludes_ctx_parameter_from_params() -> None:
    @agent(name="a", description="d", version="0.1.0")
    class OneSkillAgent:
        @skill(description="d")
        async def run(self, a: str, b: int, ctx: Context) -> str:
            return a

    meta = agent_meta(OneSkillAgent())
    assert meta is not None
    param_names = [p.name for p in meta.skills[0].params]
    assert param_names == ["a", "b"]
    assert "ctx" not in param_names

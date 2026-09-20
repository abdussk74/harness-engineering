"""ctx.llm's Ollama provider: constructs a real langchain-ollama
ChatOllama (lazily, no running server needed for construction), so
agents can develop entirely offline without spending API tokens."""

from __future__ import annotations

from langchain_ollama import ChatOllama

from harness.llm.client import build_chat_model


async def test_ollama_provider_builds_chat_ollama_lazily() -> None:
    chat = build_chat_model(
        provider="ollama", model="llama3.2", ollama_base_url="http://localhost:11434"
    )

    assert chat._model is None  # noqa: SLF001 - asserting the laziness contract directly

    model = chat._build()  # noqa: SLF001

    assert isinstance(model, ChatOllama)
    assert model.base_url == "http://localhost:11434"
    assert model.model == "llama3.2"


def test_ollama_provider_requires_an_explicit_model() -> None:
    try:
        build_chat_model(provider="ollama", model=None)
    except ValueError as exc:
        assert "HARNESS_LLM_MODEL" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing model")

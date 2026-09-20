"""ctx.llm — a LangChain chat model wrapped with GenAI OTel spans.

LangSmith tracing is layered independently, not reimplemented here:
LangChain traces to LangSmith natively via its own callback system once
LANGSMITH_TRACING/LANGSMITH_API_KEY are set in the process environment
(harness.config.load_env_file() ensures `.env` actually reaches
os.environ, since LangChain reads those vars directly, never through
HarnessConfig). This wrapper's only job is the OTel side.

The underlying LangChain client is built lazily, on first `ainvoke()`,
not at construction — so an agent whose skills never touch `ctx.llm`
never has to have an API key (or a running Ollama server) configured
at all.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from harness.telemetry.genai import genai_span

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-5",
}


class TracedChatModel:
    """Same `.ainvoke()` shape as a LangChain chat model, plus an OTel
    GenAI span around each call."""

    def __init__(
        self,
        *,
        provider: str,
        model_name: str,
        model: BaseChatModel | None = None,
        ollama_base_url: str = "http://localhost:11434",
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._model = model
        self._ollama_base_url = ollama_base_url

    def _build(self) -> BaseChatModel:
        if self._provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=self._model_name)  # type: ignore[call-arg]
        if self._provider == "openai":
            try:
                from langchain_openai import ChatOpenAI  # type: ignore[import-not-found]
            except ImportError as exc:
                raise ImportError(
                    "The openai provider requires langchain-openai — install a2a-harness[openai]."
                ) from exc
            model: BaseChatModel = ChatOpenAI(model=self._model_name)
            return model
        if self._provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(model=self._model_name, base_url=self._ollama_base_url)
        raise ValueError(f"Unknown LLM provider '{self._provider}'.")

    async def ainvoke(self, prompt: str) -> BaseMessage:
        if self._model is None:
            self._model = self._build()
        with genai_span(provider=self._provider, model=self._model_name):
            return await self._model.ainvoke(prompt)


def build_chat_model(
    *, provider: str | None, model: str | None, ollama_base_url: str = "http://localhost:11434"
) -> TracedChatModel:
    resolved_provider = provider or "anthropic"
    resolved_model = model or _DEFAULT_MODELS.get(resolved_provider)
    if resolved_model is None:
        raise ValueError(
            f"No default model for provider '{resolved_provider}'; set HARNESS_LLM_MODEL."
        )
    return TracedChatModel(
        provider=resolved_provider, model_name=resolved_model, ollama_base_url=ollama_base_url
    )

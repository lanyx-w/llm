"""LLM transport layer.

``ChatModel`` is the port the agent depends on; ``OpenAIChatModel`` is one
adapter. Adding an Ollama/Anthropic/other provider only requires a new adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol, Sequence

from openai import OpenAI

from .config import LLMConfig


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    """Incremental fragment of a tool call inside a streamed chunk."""

    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """Provider-neutral representation of a streamed chunk."""

    content: str = ""
    tool_calls: tuple[ToolCallDelta, ...] = ()


class ChatModel(Protocol):
    """Port for any streaming chat-completion provider."""

    def stream(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict] | None = None,
    ) -> Iterator[StreamChunk]:
        """Yield chunks for ``messages``, optionally exposing tools."""


class OpenAIChatModel:
    """Adapter for any OpenAI-compatible chat-completions API."""

    def __init__(self, config: LLMConfig, client: OpenAI | None = None) -> None:
        self._config = config
        self._client = client or OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )

    @property
    def model_name(self) -> str:
        return self._config.model_name

    def stream(
        self,
        messages: Sequence[dict],
        tools: Sequence[dict] | None = None,
    ) -> Iterator[StreamChunk]:
        kwargs: dict = {
            "model": self._config.model_name,
            "messages": list(messages),
            "stream": True,
        }
        if tools:
            kwargs["tools"] = list(tools)

        for chunk in self._client.chat.completions.create(**kwargs):
            yield self._parse_chunk(chunk)

    @staticmethod
    def _parse_chunk(chunk) -> StreamChunk:
        choices = getattr(chunk, "choices", None)
        if not choices:
            return StreamChunk()

        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return StreamChunk()

        content = getattr(delta, "content", None) or ""
        tool_calls = []
        for item in getattr(delta, "tool_calls", None) or []:
            function = getattr(item, "function", None)
            tool_calls.append(
                ToolCallDelta(
                    index=item.index,
                    id=getattr(item, "id", None) or "",
                    name=getattr(function, "name", None) or "",
                    arguments=getattr(function, "arguments", None) or "",
                )
            )

        return StreamChunk(content=content, tool_calls=tuple(tool_calls))

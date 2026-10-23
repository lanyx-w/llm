"""UI-agnostic agent loop.

``Agent.send`` is a generator that yields :mod:`core.events` objects. Front-ends
only iterate over the events, which keeps the conversation/tool orchestration
independent of any rendering technology.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .cancellation import CancellationToken
from .events import (
    AgentError,
    AgentEvent,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCancelled,
    TurnCompleted,
)
from .llm import ChatModel
from .tools.base import ToolRegistry

DEFAULT_SYSTEM_PROMPT = (
    "你是一个可靠的本地助手，可以使用工具读写文件、查询系统信息。"
    "在需要操作文件系统时优先调用工具，而不是凭空猜测。"
    "工具出错时请说明原因，不要编造结果。"
)

DEFAULT_MAX_STEPS = 8


class _TurnCancelled(Exception):
    """Internal signal used to unwind the turn when the user cancels."""


@dataclass
class _ToolCall:
    id: str = ""
    name: str = ""
    arguments: str = ""

    def to_message(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


class Agent:
    """Owns conversation state and drives the LLM/tool loop."""

    def __init__(
        self,
        model: ChatModel,
        tools: ToolRegistry,
        system_prompt: str | None = DEFAULT_SYSTEM_PROMPT,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> None:
        self._model = model
        self._tools = tools
        self._system_prompt = system_prompt
        self._max_steps = max_steps
        self._messages: list[dict] = []
        self._reset_messages()

    @property
    def messages(self) -> list[dict]:
        """A shallow copy of the conversation history."""
        return list(self._messages)

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    @property
    def max_steps(self) -> int:
        """Maximum number of model calls per user turn."""
        return self._max_steps

    def reset(self) -> None:
        self._reset_messages()

    def send(
        self,
        content: str,
        cancel: CancellationToken | None = None,
    ) -> Iterator[AgentEvent]:
        """Process one user message and stream the resulting events.

        The generator finishes after :class:`TurnCompleted`,
        :class:`TurnCancelled` or :class:`AgentError`. Cancelled and failed
        turns are removed from the history, so only completed exchanges are
        remembered.
        """
        text = (content or "").strip()
        if not text:
            return

        turn_start = len(self._messages)
        self._messages.append({"role": "user", "content": text})

        try:
            for _step in range(self._max_steps):
                if cancel is not None and cancel.cancelled:
                    raise _TurnCancelled

                reply, tool_calls = yield from self._stream_once(cancel)

                if not tool_calls:
                    self._messages.append({"role": "assistant", "content": reply})
                    yield TurnCompleted(reply)
                    return

                self._messages.append(
                    {
                        "role": "assistant",
                        "content": reply or None,
                        "tool_calls": [call.to_message() for call in tool_calls],
                    }
                )

                for call in tool_calls:
                    if cancel is not None and cancel.cancelled:
                        raise _TurnCancelled

                    yield ToolCallStarted(
                        call_id=call.id,
                        name=call.name,
                        arguments=call.arguments,
                    )
                    output = self._tools.dispatch(call.name, call.arguments)
                    if cancel is not None and cancel.cancelled:
                        raise _TurnCancelled

                    yield ToolCallFinished(
                        call_id=call.id,
                        name=call.name,
                        arguments=call.arguments,
                        output=output,
                    )
                    self._messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": output,
                        }
                    )

            raise RuntimeError(f"本轮模型调用次数已达上限（{self._max_steps}）")
        except _TurnCancelled:
            self._truncate(turn_start)
            yield TurnCancelled()
        except Exception as exc:  # noqa: BLE001 - surface errors as events
            self._truncate(turn_start)
            yield AgentError(str(exc))

    def _stream_once(
        self,
        cancel: CancellationToken | None = None,
    ) -> Iterator[AgentEvent]:
        """Stream one LLM response, yielding text deltas.

        Returns ``(reply, tool_calls)`` once the stream is exhausted.
        """
        reply_parts: list[str] = []
        tool_calls: list[_ToolCall] = []

        for chunk in self._model.stream(self._messages, self._tools.schemas()):
            if cancel is not None and cancel.cancelled:
                raise _TurnCancelled

            if chunk.content:
                reply_parts.append(chunk.content)
                yield TextDelta(chunk.content)

            for delta in chunk.tool_calls:
                while len(tool_calls) <= delta.index:
                    tool_calls.append(_ToolCall())
                slot = tool_calls[delta.index]
                slot.id += delta.id
                slot.name += delta.name
                slot.arguments += delta.arguments

        for index, call in enumerate(tool_calls):
            if not call.id:
                call.id = f"call_{index}"

        return "".join(reply_parts), tool_calls

    def _truncate(self, index: int) -> None:
        del self._messages[index:]

    def _reset_messages(self) -> None:
        self._messages = []
        if self._system_prompt:
            self._messages.append(
                {"role": "system", "content": self._system_prompt}
            )

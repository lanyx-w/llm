"""Events emitted by the agent while it processes a turn.

The UI layer consumes these events and never has to know how the LLM or the
tools work internally. Any front-end (TUI, Web, Desktop) can subscribe to the
same stream.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextDelta:
    """A chunk of assistant text produced by the streaming LLM."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    """The agent is about to execute a tool call."""

    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ToolCallFinished:
    """A tool call finished and produced a textual result."""

    call_id: str
    name: str
    arguments: str
    output: str


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    """The assistant finished the whole turn (no more tool calls)."""

    reply: str


@dataclass(frozen=True, slots=True)
class TurnCancelled:
    """The turn was cancelled; it was removed from the conversation history."""


@dataclass(frozen=True, slots=True)
class AgentError:
    """The turn failed; the message is safe to display to the user."""

    message: str


AgentEvent = (
    TextDelta
    | ToolCallStarted
    | ToolCallFinished
    | TurnCompleted
    | TurnCancelled
    | AgentError
)

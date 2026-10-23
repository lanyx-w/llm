"""Reusable widgets for the terminal front-end."""

from __future__ import annotations

import json

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Markdown, Static


class UserMessage(Vertical):
    """A user turn."""

    def __init__(self, text: str) -> None:
        super().__init__(classes="message user")
        self._body = Static(Text(text), classes="body")

    def compose(self) -> ComposeResult:
        yield Label("你", classes="role")
        yield self._body


class AssistantMessage(Vertical):
    """An assistant turn that can be updated while streaming."""

    def __init__(self, text: str = "") -> None:
        super().__init__(classes="message assistant")
        self._text = text
        self._body = Markdown(text, classes="body")

    def compose(self) -> ComposeResult:
        yield Label("wAgent", classes="role")
        yield self._body

    def on_mount(self) -> None:
        self._body.update(self._text)

    def append_text(self, text: str) -> None:
        self._text += text
        if self.is_mounted:
            self._body.update(self._text)


class ToolCallBlock(Vertical):
    """A collapsible tool invocation card.

    Collapsed by default; click the card to show arguments and the result.
    """

    def __init__(self, name: str, arguments: str) -> None:
        super().__init__(classes="message tool")
        self._name = name
        self._raw_arguments = arguments
        self._expanded = False
        self._ms: float | None = None
        self._output = "运行中…"
        self._header = Static(Text(""), classes="tool-header")
        self._details = Static(Text(""), classes="tool-details")
        self._details.display = self._expanded
        self._render_header()
        self._render_details()

    def compose(self) -> ComposeResult:
        yield self._header
        yield self._details

    def on_click(self, event) -> None:
        event.stop()
        self.toggle()

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._details.display = self._expanded
        self._render_header()
        if self._expanded:
            self._render_details()

    def set_output(self, output: str, elapsed_ms: float) -> None:
        self._output = output
        self._ms = elapsed_ms
        self._render_header()
        self._render_details()

    def _render_header(self) -> None:
        arrow = "▼" if self._expanded else "▶"
        timing = "运行中…" if self._ms is None else f"{self._ms:.0f} ms"
        text = Text()
        text.append(f"{arrow} ", style="bold")
        text.append(self._name, style="bold")
        text.append(_summarize_arguments(self._raw_arguments))
        text.append(" · " + timing, style="dim")
        self._header.update(text)

    def _render_details(self) -> None:
        text = Text()
        text.append("参数\n", style="bold")
        text.append(_pretty_arguments(self._raw_arguments) + "\n\n", style="dim")
        text.append("结果\n", style="bold")
        text.append(self._output)
        self._details.update(text)


class NoticeMessage(Vertical):
    """Informational or error text shown inline in the transcript."""

    def __init__(self, text: str, *, severity: str = "info") -> None:
        super().__init__(classes=f"message notice {severity}")
        self._body = Static(Text(text), classes="body")
        self._title = "错误" if severity == "error" else "提示"

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="role")
        yield self._body


def _summarize_arguments(arguments: str) -> str:
    data = _parse_arguments(arguments)
    if not isinstance(data, dict):
        return f"({arguments})"
    if not data:
        return "()"

    parts = []
    for key, value in data.items():
        if isinstance(value, str):
            preview = value.replace("\n", "\\n")
            if len(preview) > 24:
                preview = preview[:24] + "…"
            parts.append(f"{key}={preview}")
        else:
            parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    return "(" + ", ".join(parts) + ")"


def _pretty_arguments(arguments: str) -> str:
    data = _parse_arguments(arguments)
    if data is None:
        return arguments or "{}"
    return json.dumps(data, ensure_ascii=False, indent=2)


def _parse_arguments(arguments: str):
    try:
        return json.loads(arguments) if arguments and arguments.strip() else {}
    except json.JSONDecodeError:
        return None

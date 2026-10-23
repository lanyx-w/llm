"""Textual front-end.

This module is the only place that knows about Textual. It translates core
events into widgets and never contains agent/LLM logic.
"""

from __future__ import annotations

import os
import time
import uuid

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Static

from core.agent import Agent
from core.cancellation import CancellationToken
from core.events import (
    AgentError,
    AgentEvent,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCancelled,
    TurnCompleted,
)

from .help_screen import HelpScreen
from .widgets import (
    AssistantMessage,
    NoticeMessage,
    ToolCallBlock,
    UserMessage,
)

HELP_TEXT = (
    "命令：/help 帮助 · /clear 清屏 · /new 新会话 · /tools 工具 · "
    "/cwd 目录 · /model 模型 · /quit 退出\n"
    "快捷键：Ctrl+X 退出 · Ctrl+N 新会话 · Ctrl+B 侧栏 · F1 帮助 · Esc 中断"
)


class AgentTUI(App):
    """Terminal client for :class:`core.agent.Agent`."""

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("ctrl+x", "quit", "退出", priority=True),
        Binding("ctrl+l", "clear_transcript", "清屏"),
        Binding("ctrl+n", "new_session", "新会话"),
        Binding("ctrl+b", "toggle_sidebar", "侧栏"),
        Binding("f1", "help", "帮助"),
        Binding("f2", "help", "帮助", show=False),
        Binding("escape", "interrupt", "中断", show=False),
    ]

    def __init__(self, agent: Agent, model_name: str, base_url: str) -> None:
        super().__init__()
        self._agent = agent
        self._model_name = model_name
        self._base_url = base_url
        self._cwd = os.getcwd()

        self._busy = False
        self._state = "就绪"
        self._state_kind = "ready"
        self._assistant: AssistantMessage | None = None
        self._tool_blocks: dict[str, ToolCallBlock] = {}
        self._tool_started: dict[str, float] = {}

        self._session_id = uuid.uuid4().hex[:8]
        self._tool_count = 0
        self._last_duration = 0.0
        self._turn_started = 0.0
        self._cancel: CancellationToken | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="main"):
                yield Static("", id="info")
                yield VerticalScroll(id="transcript")
            with VerticalScroll(id="sidebar"):
                yield Static("", id="sidebar-body")
        yield Static("", id="status")
        yield Input(
            placeholder="输入问题后 Enter 发送；/help 查看命令；Esc 中断生成",
            id="prompt",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "wAgent"
        self.sub_title = f"{self._model_name} · {self._cwd}"
        self._add_notice("wAgent 已启动。输入问题开始对话，按 F1 查看帮助。")
        self._refresh_header_panels()
        self._refresh_status()
        self.query_one("#prompt", Input).focus()

    # ------------------------------------------------------------------ input

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""

        if not text:
            return
        if self._busy:
            self.notify("请等待当前回复完成，或按 Esc 中断", severity="warning")
            return
        if text.startswith("/"):
            self._run_command(text)
            return

        self._start_turn(text)

    def _run_command(self, command: str) -> None:
        name = command.split(maxsplit=1)[0].lower()
        if name in {"/quit", "/exit"}:
            self.exit()
        elif name == "/help":
            self.action_help()
        elif name == "/clear":
            self.action_clear_transcript()
        elif name in {"/new", "/reset"}:
            self.action_new_session()
        elif name == "/tools":
            self._show_tools()
        elif name == "/cwd":
            self._add_notice(f"工作目录：{self._cwd}")
        elif name == "/model":
            self._add_notice(
                f"模型：{self._model_name}\n接口：{self._base_url}"
            )
        else:
            self.notify(f"未知命令: {command}", severity="warning")

    # ------------------------------------------------------------------ turn

    def _start_turn(self, text: str) -> None:
        self._busy = True
        self._assistant = None
        self._tool_blocks.clear()
        self._tool_started.clear()
        self._cancel = CancellationToken()
        self._turn_started = time.perf_counter()
        self._set_state("思考中…", "busy")

        self._append(UserMessage(text))
        self._scroll_end()
        self._refresh_status()

        self._run_agent(text, self._cancel)

    @work(thread=True, exclusive=True)
    def _run_agent(self, text: str, cancel: CancellationToken) -> None:
        try:
            for event in self._agent.send(text, cancel=cancel):
                self._dispatch(event)
        except Exception as exc:  # noqa: BLE001 - keep UI alive
            self._dispatch(AgentError(str(exc)))

    def _dispatch(self, event: AgentEvent) -> None:
        try:
            self.call_from_thread(self._handle_event, event)
        except RuntimeError:
            pass

    # --------------------------------------------------------------- events

    def _handle_event(self, event: AgentEvent) -> None:
        if isinstance(event, TextDelta):
            self._on_text(event.text)
        elif isinstance(event, ToolCallStarted):
            self._on_tool_started(event)
        elif isinstance(event, ToolCallFinished):
            self._on_tool_finished(event)
        elif isinstance(event, TurnCompleted):
            self._on_turn_completed(event)
        elif isinstance(event, TurnCancelled):
            self._on_turn_cancelled()
        elif isinstance(event, AgentError):
            self._on_error(event)

    def _on_text(self, text: str) -> None:
        if self._assistant is None:
            self._assistant = AssistantMessage(text)
            self._append(self._assistant)
        else:
            self._assistant.append_text(text)
        self._set_state("生成中…", "busy")
        self._scroll_end()

    def _on_tool_started(self, event: ToolCallStarted) -> None:
        self._assistant = None
        block = ToolCallBlock(event.name, event.arguments)
        self._tool_blocks[event.call_id] = block
        self._tool_started[event.call_id] = time.perf_counter()
        self._tool_count += 1
        self._append(block)
        self._set_state(f"调用工具: {event.name}", "busy")
        self._refresh_status()
        self._scroll_end()

    def _on_tool_finished(self, event: ToolCallFinished) -> None:
        block = self._tool_blocks.pop(event.call_id, None)
        started = self._tool_started.pop(event.call_id, None)
        elapsed_ms = (
            (time.perf_counter() - started) * 1000 if started is not None else 0.0
        )
        if block is not None:
            block.set_output(event.output, elapsed_ms)
        self._set_state("处理工具结果…", "busy")
        self._scroll_end()

    def _on_turn_completed(self, event: TurnCompleted) -> None:
        self._last_duration = time.perf_counter() - self._turn_started
        self._finish_turn("就绪", "ready")

    def _on_turn_cancelled(self) -> None:
        self._last_duration = time.perf_counter() - self._turn_started
        self._add_notice("已中断当前生成，本轮内容未写入历史。")
        self._finish_turn("已中断", "cancelled")

    def _on_error(self, event: AgentError) -> None:
        self._last_duration = time.perf_counter() - self._turn_started
        self._append(NoticeMessage(event.message, severity="error"))
        self._finish_turn("错误", "error")

    # --------------------------------------------------------------- helpers

    def _finish_turn(self, state: str, kind: str) -> None:
        self._busy = False
        self._cancel = None
        self._assistant = None
        self._tool_blocks.clear()
        self._tool_started.clear()
        self._set_state(state, kind)
        self.query_one("#prompt", Input).focus()
        self._refresh_header_panels()
        self._refresh_status()
        self._scroll_end()

    def _set_state(self, state: str, kind: str) -> None:
        self._state = state
        self._state_kind = kind
        self._refresh_status()

    def _conversation_stats(self) -> tuple[int, int]:
        messages = self._agent.messages
        rounds = sum(1 for message in messages if message.get("role") == "user")
        visible = sum(
            1
            for message in messages
            if message.get("role") in {"user", "assistant"}
            and message.get("content")
            and not message.get("tool_calls")
        )
        return rounds, visible

    def _append(self, widget) -> None:
        self.query_one("#transcript", VerticalScroll).mount(widget)

    def _add_notice(self, text: str, *, severity: str = "info") -> None:
        self._append(NoticeMessage(text, severity=severity))
        self._scroll_end()

    def _scroll_end(self) -> None:
        self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)

    def _show_tools(self) -> None:
        specs = self._agent.tools.specs
        lines = [f"已注册 {len(specs)} 个工具："]
        lines.extend(f"· {spec.name} — {spec.description}" for spec in specs)
        self._add_notice("\n".join(lines))

    # ----------------------------------------------------------- rendering

    def _refresh_header_panels(self) -> None:
        self._render_info()
        self._render_sidebar()

    def _render_info(self) -> None:
        tool_count = len(self._agent.tools.specs)
        text = Text()
        text.append("wAgent", style="bold cyan")
        text.append(f"  ·  {tool_count} 个工具  ·  {self._model_name}\n")
        text.append("工作目录  ", style="dim")
        text.append(self._cwd + "\n")
        text.append(
            "Enter 发送    /help 命令    Esc 中断生成    "
            "Ctrl+B 侧栏    Ctrl+N 新会话",
            style="dim",
        )
        self.query_one("#info", Static).update(text)

    def _render_sidebar(self) -> None:
        rounds, visible = self._conversation_stats()
        text = Text()
        text.append("会话\n", style="bold")
        rows = (
            ("模型", self._model_name),
            ("接口", self._base_url),
            ("目录", self._cwd),
            ("会话", self._session_id),
            ("轮次", str(rounds)),
            ("消息", str(visible)),
            ("上限", f"{self._agent.max_steps} 次模型调用/轮"),
            ("状态", self._state),
        )
        for label, value in rows:
            text.append(f"{label}  ", style="dim")
            text.append(value + "\n")

        specs = self._agent.tools.specs
        text.append(f"\n工具 · {len(specs)}\n", style="bold")
        for index, spec in enumerate(specs):
            text.append(f"● {spec.name}\n", style="bold cyan")
            text.append(f"  {spec.description}\n", style="dim")
            if index < len(specs) - 1:
                text.append("\n")

        self.query_one("#sidebar-body", Static).update(text)

    def _refresh_status(self) -> None:
        rounds, _ = self._conversation_stats()
        colors = {
            "ready": "green",
            "busy": "yellow",
            "cancelled": "magenta",
            "error": "red",
        }
        color = colors.get(self._state_kind, "green")
        duration = f"{self._last_duration:.1f}s"

        text = Text()
        text.append("● ", style=f"bold {color}")
        text.append(self._state, style=f"bold {color}")
        text.append(f" · {rounds} 轮 · {self._model_name}")
        text.append(f"   |   工具 {self._tool_count} 次   |   {duration}   |   ")
        text.append("Esc 中断", style="dim")
        self.query_one("#status", Static).update(text)

    # ------------------------------------------------------------- actions

    def action_clear_transcript(self) -> None:
        self.query_one("#transcript", VerticalScroll).remove_children()
        self._add_notice("界面已清空（对话历史保留）。")

    def action_new_session(self) -> None:
        self._agent.reset()
        self._session_id = uuid.uuid4().hex[:8]
        self._tool_count = 0
        self._last_duration = 0.0
        self._state = "就绪"
        self._state_kind = "ready"
        self.query_one("#transcript", VerticalScroll).remove_children()
        self._add_notice(f"已新建会话 {self._session_id}。")
        self._refresh_header_panels()
        self._refresh_status()
        self.query_one("#prompt", Input).focus()

    def action_toggle_sidebar(self) -> None:
        self.query_one("#sidebar").toggle_class("hidden")

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_interrupt(self) -> None:
        if self._busy and self._cancel is not None:
            self._cancel.cancel()
            self._set_state("中断中…", "busy")
        else:
            self.query_one("#prompt", Input).focus()

"""Modal help screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Markdown

HELP_MARKDOWN = """\
# wAgent 帮助

## 使用方式

- 在底部输入框输入问题，`Enter` 发送。
- 模型需要查看/修改文件时会自动调用工具，工具卡片可点击展开。
- `Esc` 中断当前生成；已完成的问答才会写入历史。

## 命令

| 命令 | 作用 |
| --- | --- |
| `/help` | 打开本帮助 |
| `/clear` | 清空界面（保留历史） |
| `/new` | 新建会话（重置历史） |
| `/tools` | 列出已注册工具 |
| `/cwd` | 显示工作目录 |
| `/model` | 显示模型与接口 |
| `/quit` | 退出 |

## 快捷键

| 快捷键 | 作用 |
| --- | --- |
| `Enter` | 发送消息 |
| `Esc` | 中断生成 / 关闭弹窗 |
| `F1` / `F2` | 打开帮助（VSCode 中 F1 可能被占用，可用 F2） |
| `Ctrl+B` | 显示 / 隐藏侧栏 |
| `Ctrl+N` | 新建会话 |
| `Ctrl+L` | 清屏 |
| `Ctrl+X` | 退出 |

---

按 `Esc` 或 `F1` 关闭本帮助。
"""


class HelpScreen(ModalScreen):
    """A dismissible overlay with usage, commands and shortcuts."""

    BINDINGS = [
        Binding("escape", "dismiss", "关闭", show=False),
        Binding("f1", "dismiss", "关闭", show=False),
        Binding("f2", "dismiss", "关闭", show=False),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
        background: $background 60%;
    }

    #help-dialog {
        width: 76%;
        height: 84%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-dialog"):
            yield Markdown(HELP_MARKDOWN, id="help-body")

    def action_dismiss(self) -> None:
        self.dismiss()

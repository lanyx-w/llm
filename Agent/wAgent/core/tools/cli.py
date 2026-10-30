"""Command-line tool: run any installed CLI program without a shell."""

from __future__ import annotations

import json
import locale
import os
import subprocess

from .base import ToolSpec

_TIMEOUT_SECONDS = 30
_MAX_OUTPUT_CHARS = 8000


def _decode(data: bytes | None) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _format_stream(label: str, data: bytes | None) -> str:
    text = _decode(data).rstrip()
    if not text:
        return "{}: （无）".format(label)
    if len(text) > _MAX_OUTPUT_CHARS:
        return "{}（已截断，仅显示前 {} 个字符，原始长度 {}）:\n{}\n...（输出过长，已截断）".format(
            label,
            _MAX_OUTPUT_CHARS,
            len(text),
            text[:_MAX_OUTPUT_CHARS].rstrip(),
        )
    return "{}:\n{}".format(label, text)


def run_cli(command: str, args: list[str] | None = None) -> str:
    name = str(command or "").strip()
    if not name:
        return "参数错误: command 不能为空"

    if args is None:
        args = []
    if not isinstance(args, (list, tuple)):
        return "参数错误: args 必须是字符串列表"

    arguments: list[str] = []
    for item in args:
        if isinstance(item, (str, int, float)) and not isinstance(item, bool):
            arguments.append(str(item))
        elif isinstance(item, bool):
            arguments.append("true" if item else "false")
        else:
            return "参数错误: args 中的每一项都必须是字符串"

    command_line = [name, *arguments]
    header = "命令: {}\n工作目录: {}".format(
        json.dumps(command_line, ensure_ascii=False), os.getcwd()
    )

    try:
        result = subprocess.run(
            command_line,
            shell=False,
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return "\n".join(
            (
                header,
                "状态: 执行超时（超过 {} 秒），进程已被终止".format(_TIMEOUT_SECONDS),
                _format_stream("标准输出", exc.stdout),
                _format_stream("标准错误", exc.stderr),
            )
        )
    except FileNotFoundError:
        return "\n".join(
            (
                header,
                "状态: 命令不存在或无法执行，请确认程序已安装并位于 PATH 中",
            )
        )
    except OSError as exc:
        return "\n".join((header, "状态: 启动命令失败: {}".format(exc)))

    return "\n".join(
        (
            header,
            "退出码: {}".format(result.returncode),
            _format_stream("标准输出", result.stdout),
            _format_stream("标准错误", result.stderr),
        )
    )


CLI_TOOLS = (
    ToolSpec(
        name="RunCli",
        description=(
            "调用本机已安装的任意命令行程序（CLI），例如 git、python、pip、dir 等。"
            "命令名放在 command 中，参数按顺序放入 args 数组；"
            "工具直接执行程序而不经过 Shell，因此不支持管道、重定向、通配符等 Shell 语法。"
            "返回标准输出、标准错误和退出码，供判断执行结果；"
            "默认超时 30 秒，超长输出会被截断。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的程序名称或路径，例如 git、python、C:\\\\Windows\\\\System32\\\\whoami.exe",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "传给程序的参数列表，例如 [\"status\", \"--short\"]；省略表示无参数",
                },
            },
            "required": ["command"],
        },
        handler=run_cli,
    ),
)

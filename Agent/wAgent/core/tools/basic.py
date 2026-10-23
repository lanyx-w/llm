"""Basic system tools: date/time, leap year, current working directory."""

from __future__ import annotations

import os

from .base import ToolSpec
from .helpers import run_command


def get_date() -> str:
    if os.name == "nt":
        date_text = run_command(["cmd", "/c", "date", "/t"])
        time_text = run_command(["cmd", "/c", "time", "/t"])
        return " ".join(part for part in (date_text, time_text) if part)
    return run_command(["date", "+%Y-%m-%d %H:%M:%S"])


def is_leap_year(year: int) -> str:
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    return "{}年{}是闰年".format(year, "" if leap else "不")


def get_cwd() -> str:
    return os.getcwd()


BASIC_TOOLS = (
    ToolSpec(
        name="getDate",
        description="获取当前电脑的日期和时间（调用本地 date 命令，而不是用 Python 计算）",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=get_date,
    ),
    ToolSpec(
        name="isLeapYear",
        description="判断给定的年份是否是闰年",
        parameters={
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "要判断的年份，例如 2024",
                }
            },
            "required": ["year"],
        },
        handler=is_leap_year,
    ),
    ToolSpec(
        name="getCwd",
        description="获取当前工作目录的绝对路径",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=get_cwd,
    ),
)

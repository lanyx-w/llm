"""Tool abstraction and registry.

A tool bundles its OpenAI JSON schema with its Python implementation. The
registry owns discovery (schemas) and dispatching (name -> handler), so the
agent loop stays free of tool-specific ``if`` branches.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Callable

ToolHandler = Callable[..., str]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A callable tool with its LLM-facing schema."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def invoke(self, arguments: str) -> str:
        """Parse ``arguments`` and call the handler, never raising."""
        try:
            args = json.loads(arguments) if arguments and arguments.strip() else {}
        except json.JSONDecodeError:
            return "参数解析失败: " + arguments

        if not isinstance(args, dict):
            return "参数解析失败: 参数必须是 JSON 对象"

        try:
            return self.handler(**args)
        except TypeError as exc:
            return f"参数错误: {exc}"
        except Exception as exc:  # noqa: BLE001 - tools must not break the loop
            return f"工具执行失败: {exc}"


class ToolRegistry:
    """An ordered collection of tools addressable by name."""

    def __init__(self, tools: Iterable[ToolSpec] = ()) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self.extend(tools)

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"重复注册工具: {tool.name}")
        self._tools[tool.name] = tool

    def extend(self, tools: Iterable[ToolSpec]) -> None:
        for tool in tools:
            self.register(tool)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def dispatch(self, name: str, arguments: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return "未知工具: " + name
        return tool.invoke(arguments)

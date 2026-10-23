"""Tool layer: specs, registry and built-in tools."""

from .base import ToolRegistry, ToolSpec
from .basic import BASIC_TOOLS
from .filesystem import FILESYSTEM_TOOLS

__all__ = [
    "BASIC_TOOLS",
    "FILESYSTEM_TOOLS",
    "ToolRegistry",
    "ToolSpec",
    "build_default_registry",
]


def build_default_registry() -> ToolRegistry:
    """Return a registry containing every built-in tool."""
    registry = ToolRegistry()
    registry.extend(BASIC_TOOLS)
    registry.extend(FILESYSTEM_TOOLS)
    return registry

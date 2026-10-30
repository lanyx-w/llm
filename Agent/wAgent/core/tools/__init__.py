"""Tool layer: specs, registry and built-in tools."""

from ..config import SearchConfig
from ..skills import SkillRegistry, build_skill_tools
from .base import ToolRegistry, ToolSpec
from .basic import BASIC_TOOLS
from .cli import CLI_TOOLS
from .filesystem import FILESYSTEM_TOOLS
from .search import build_search_tools
from .web import WEB_TOOLS

__all__ = [
    "BASIC_TOOLS",
    "CLI_TOOLS",
    "FILESYSTEM_TOOLS",
    "WEB_TOOLS",
    "ToolRegistry",
    "ToolSpec",
    "build_default_registry",
    "build_search_tools",
]


def build_default_registry(
    search_config: SearchConfig | None = None,
    skill_registry: SkillRegistry | None = None,
) -> ToolRegistry:
    """Return a registry containing every built-in tool."""
    skills = skill_registry or SkillRegistry.discover()
    registry = ToolRegistry()
    registry.extend(BASIC_TOOLS)
    registry.extend(CLI_TOOLS)
    registry.extend(FILESYSTEM_TOOLS)
    registry.extend(WEB_TOOLS)
    registry.extend(build_search_tools(search_config))
    registry.extend(build_skill_tools(skills))
    return registry

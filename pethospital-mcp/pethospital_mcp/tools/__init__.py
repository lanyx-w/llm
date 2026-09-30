"""MCP 工具注册。"""

from __future__ import annotations

from mcp.server import MCPServer

from ..petapi import PetApi
from . import create_pet, list_pets


def register_tools(server: MCPServer, api: PetApi) -> None:
    """按固定顺序注册全部工具（后续扩展在此追加）。"""
    list_pets.register(server, api)
    create_pet.register(server, api)

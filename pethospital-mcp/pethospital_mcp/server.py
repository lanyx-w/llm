"""装配 MCPServer：注册工具、暴露 stdio 与 Streamable HTTP 两种传输。

双传输共用这一份装配（build_server）；SDK 按 MCP-Protocol-Version 头自动路由
新旧两代协议，本模块不实现任何握手/协议层。
"""

from __future__ import annotations

import logging

from mcp.server import CacheHint, MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .petapi import DEFAULT_UPSTREAM, PetApi
from .tools import register_tools

logger = logging.getLogger(__name__)

SERVER_NAME = "pethospital-mcp"
SERVER_VERSION = "0.2.0"


def build_server(upstream: str = DEFAULT_UPSTREAM, timeout: float = 15.0) -> MCPServer:
    """装配一个 MCPServer 实例（名称/版本/说明 + 工具 + 健康检查路由）。"""
    api = PetApi(upstream, timeout=timeout)
    server = MCPServer(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        title="宠物医院 MCP Server",
        description="把本机宠物医院 REST API 封装成 MCP 工具，提供 list_pets 与 create_pet。",
        instructions=(
            "本服务是无状态桥梁：一次 list_pets / create_pet = 一次上游 GET/POST，"
            "不携带跨调用状态。参数校验失败或上游异常时返回 is_error 结果。"
        ),
        # 工具表静态不变，为列表结果设置长效缓存提示
        cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")},
    )
    register_tools(server, api)

    @server.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        return JSONResponse({"code": 200, "message": "ok", "service": SERVER_NAME, "version": SERVER_VERSION})

    return server

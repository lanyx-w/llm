"""命令行入口：python -m pethospital_mcp [-upstream ..] [-addr ..] [-stdio|-no-stdio] [-timeout ..]。

默认仅 stdio 传输；加 -addr 额外/同时提供 Streamable HTTP（挂在 /mcp，另有 GET /health）。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from threading import Thread

from . import __version__
from .petapi import DEFAULT_UPSTREAM
from .server import build_server

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pethospital-mcp",
        description=(
            "宠物医院 MCP Server（MVP：仅 list_pets）。默认 stdio 传输；"
            "-addr 提供 Streamable HTTP 监听地址（挂载 /mcp，另有 GET /health）。"
        ),
    )
    parser.add_argument(
        "-upstream",
        default=os.environ.get("PETHOSPITAL_UPSTREAM", DEFAULT_UPSTREAM),
        help=f"上游宠物医院 API 地址（默认 {DEFAULT_UPSTREAM}，环境变量 PETHOSPITAL_UPSTREAM 可覆盖）",
    )
    parser.add_argument(
        "-addr",
        default="",
        help="HTTP 监听地址，如 127.0.0.1:18080；默认空 = 仅 stdio",
    )
    parser.add_argument(
        "-stdio",
        dest="stdio",
        default=True,
        action="store_true",
        help="启用 stdio 传输（默认 true；与 -addr 同时给出时并发运行）",
    )
    parser.add_argument(
        "-no-stdio",
        dest="stdio",
        action="store_false",
        help="关闭 stdio 传输（仅 -addr 场景使用，避免 stdout 被污染）",
    )
    parser.add_argument(
        "-timeout",
        type=float,
        default=15.0,
        help="上游请求超时秒数（默认 15）",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _configure_logging() -> None:
    # stdio 传输下 stdout 只能输出协议消息，所有日志写 stderr
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _serve_stdio(upstream: str, timeout: float) -> None:
    """独立线程运行 stdio 传输（独立装配，避免跨事件循环共享 httpx 客户端）。"""
    server = build_server(upstream, timeout=timeout)
    logger.info("stdio 传输已启动（upstream=%s）", upstream)
    server.run(transport="stdio")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    _configure_logging()

    if args.addr:
        host, _, port = args.addr.rpartition(":")
        server = build_server(args.upstream, timeout=args.timeout)
        app = server.streamable_http_app(streamable_http_path="/mcp")
        if args.stdio:
            Thread(target=_serve_stdio, args=(args.upstream, args.timeout), daemon=True).start()
        import uvicorn

        logger.info("Streamable HTTP 已启动： http://%s:%s/mcp （健康检查 GET /health）", host, port)
        uvicorn.run(app, host=host, port=int(port), log_level="info")
    else:
        _serve_stdio(args.upstream, args.timeout)


if __name__ == "__main__":
    main()

"""测试共用：线程内桩上游（httpx 真实发往本机 http.server）+ 数据构造工具。"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest


class StubState:
    """桩上游的可变状态：响应状态码 / 信封 / 延迟，以及收到的请求记录。"""

    def __init__(self) -> None:
        self.status = 200
        self.payload: dict[str, Any] = {
            "code": 200,
            "message": "ok",
            "data": {"items": [], "total": 0, "page": 1, "pageSize": 10, "totalPages": 0},
            "time": "2026-01-01T00:00:00+08:00",
        }
        self.delay = 0.0
        self.requests: list[tuple[str, list[tuple[str, str]]]] = []
        self.posts: list[tuple[str, Any]] = []


class _Handler(BaseHTTPRequestHandler):  # noqa: N801 - 保持与 stdlib 一致的命名
    def do_GET(self) -> None:  # noqa: N802 - stdlib 接口
        state: StubState = self.server.stub_state  # type: ignore[attr-defined]
        parsed = urlsplit(self.path)
        state.requests.append((parsed.path, parse_qsl(parsed.query, keep_blank_values=True)))
        self._respond()

    def do_POST(self) -> None:  # noqa: N802 - stdlib 接口
        state: StubState = self.server.stub_state  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if raw:
            try:
                body: Any = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                body = raw.decode("utf-8", errors="replace")
        else:
            body = None
        state.posts.append((urlsplit(self.path).path, body))
        self._respond()

    def _respond(self) -> None:
        state: StubState = self.server.stub_state  # type: ignore[attr-defined]
        if state.delay:
            time.sleep(state.delay)
        body = json.dumps(state.payload, ensure_ascii=False).encode("utf-8")
        self.send_response(state.status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass  # 静音访问日志


class StubServer:
    """线程内 http.server，随机空闲端口，返回可配置的统一信封。"""

    def __init__(self) -> None:
        self.state = StubState()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.stub_state = self.state  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_port}"

    def start(self) -> StubServer:
        self._thread.start()
        return self

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)

    def query_of(self, index: int = -1) -> dict[str, str]:
        """最近一次请求的查询参数（已 URL 解码）。"""
        _path, query = self.state.requests[index]
        return dict(query)


@pytest.fixture
def stub_upstream():
    server = StubServer().start()
    try:
        yield server
    finally:
        server.close()


def make_pet(
    pid: str = "PET-000001",
    name: str = "旺财",
    species: str = "犬",
    owner_name: str = "张三",
    doctor: str = "李医生",
    disease: str = "急性肠胃炎",
    status: str = "待就诊",
    total_cost: float = 1200.0,
    visit_count: int = 3,
) -> dict[str, Any]:
    return {
        "id": pid,
        "name": name,
        "species": species,
        "breed": "金毛",
        "gender": "公",
        "ageMonths": 36,
        "color": "黄",
        "ownerName": owner_name,
        "ownerPhone": "13800001111",
        "ownerAddr": "测试地址",
        "doctor": doctor,
        "disease": disease,
        "status": status,
        "allergy": "无",
        "records": [{"id": "MR-1", "diagnosis": disease}],
        "charges": [{"id": "CH-1", "amount": total_cost}],
        "totalCost": total_cost,
        "visitCount": visit_count,
        "createdAt": "2026-01-01T00:00:00+08:00",
        "updatedAt": "2026-01-01T00:00:00+08:00",
    }


def make_data(
    items: list[dict[str, Any]],
    total: int,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    total_pages = max(1, -(-total // max(page_size, 1)))
    return {"items": items, "total": total, "page": page, "pageSize": page_size, "totalPages": total_pages}

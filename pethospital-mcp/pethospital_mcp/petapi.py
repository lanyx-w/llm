"""上游「宠物医院 REST API」的异步客户端。

统一信封：{"code": 200, "message": "ok", "data": {...}, "time": "..."}。
code 不在约定成功集合、HTTP 4xx/5xx、连接失败/超时，统一抛 UpstreamError，
消息即对用户可操作的中文提示（新增接口成功码为 201）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_UPSTREAM = "http://127.0.0.1:8080"

# 响应体摘要的最大长度，防止把整条上游响应塞进错误信息
_RESPONSE_HEAD_CHARS = 200


class UpstreamError(Exception):
    """上游调用失败（连接/超时/HTTP 错误/业务 code!=200），message 可直接展示给用户。"""


def _response_head(resp: httpx.Response) -> str:
    """截取响应体前若干字符作为摘要。"""
    text = resp.text
    try:
        text = resp.text
    except Exception:  # pragma: no cover - 流式响应异常兜底
        text = ""
    if len(text) > _RESPONSE_HEAD_CHARS:
        text = text[:_RESPONSE_HEAD_CHARS] + "…(已截断)"
    return text.strip() or "(空响应体)"


class PetApi:
    """封装上游 API：本 server 无状态，一次调用 = 一次上游 GET。"""

    def __init__(self, base_url: str = DEFAULT_UPSTREAM, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        """释放底层连接池。"""
        await self._client.aclose()

    async def list_pets(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET /api/v1/pets，返回信封里的 data（items/total/page/pageSize 等）。"""
        try:
            resp = await self._client.get("/api/v1/pets", params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(
                f"无法连接上游，请确认 pethospital 是否在 {self.base_url} 运行"
            ) from exc
        return self._unwrap(resp, success_codes={200})

    async def create_pet(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/pets 新增一只宠物，返回信封里的 data（即新建的档案）。"""
        try:
            resp = await self._client.post("/api/v1/pets", json=payload)
        except httpx.HTTPError as exc:
            raise UpstreamError(
                f"无法连接上游，请确认 pethospital 是否在 {self.base_url} 运行"
            ) from exc
        # 上游新增成功统一信封 code=201（挂着 HTTP 201）
        return self._unwrap(resp, success_codes={200, 201})

    def _unwrap(self, resp: httpx.Response, success_codes: set[int]) -> dict[str, Any]:
        """解析统一信封：非 2xx/非预期 code/非法 JSON 都换算成 UpstreamError。"""
        if resp.status_code >= 400:
            raise UpstreamError(f"上游接口返回 HTTP {resp.status_code}：{_response_head(resp)}")

        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise UpstreamError(f"上游返回内容不是合法 JSON：{_response_head(resp)}") from exc

        if not isinstance(payload, dict):
            raise UpstreamError(f"上游返回的不是统一信封：{_response_head(resp)}")

        if payload.get("code") not in success_codes:
            raise UpstreamError(f"上游返回业务错误：{payload.get('message', 'unknown')}")

        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def __aenter__(self) -> PetApi:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

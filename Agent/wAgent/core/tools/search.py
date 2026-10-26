"""Web search tool backed by Baidu Qianfan AI Search (web_search)."""

from __future__ import annotations

import html
import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..config import SEARCH_API_KEY_FIELDS, SearchConfig, load_search_config
from .base import ToolSpec

_SEARCH_TIMEOUT = 30
_MAX_QUERY_CHARS = 72
_MAX_RESULTS = 10
_MAX_SNIPPET_CHARS = 300
_MAX_ERROR_CHARS = 500
_SEARCH_SOURCE = "baidu_search_v2"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_PERMISSION_HINT = (
    "\n提示：该接口只需 API Key，无需 appid。"
    "请确认百度千帆 API Key 有效，且已开通「百度AI搜索」权限。"
)


@dataclass(frozen=True, slots=True)
class _SearchResult:
    title: str
    url: str
    snippet: str = ""
    website: str = ""
    date: str = ""


def _with_permission_hint(message: str) -> str:
    lowered = message.lower()
    if any(
        token in lowered
        for token in ("appid", "permission", "authentication", "unauthorized")
    ):
        return message + _PERMISSION_HINT
    return message


def _missing_config_message(config: SearchConfig) -> str:
    location = config.config_path or "config.ini"
    return (
        "未配置百度千帆搜索 API Key。请在 {} 的 [search] 段设置 "
        "baiduqianfan_api_key（兼容 {}）。"
    ).format(location, ", ".join(SEARCH_API_KEY_FIELDS[1:]))


def _prepare_query(query: str) -> tuple[str, bool]:
    query = str(query or "").strip()
    if not query:
        return "", False

    units = 0
    chars: list[str] = []
    for char in query:
        cost = 2 if ord(char) > 127 else 1
        if units + cost > _MAX_QUERY_CHARS:
            return "".join(chars), True
        units += cost
        chars.append(char)
    return query, False


def _clean_snippet(value: str) -> str:
    text = html.unescape(value)
    text = _HTML_TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return None
    for encoding in ("utf-8", "gb18030"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None


def _api_error(data: dict[str, Any]) -> str:
    code = data.get("code")
    message = data.get("message") or data.get("msg")
    error = data.get("error")

    if isinstance(error, dict):
        if code is None:
            code = error.get("code")
        message = message or error.get("message") or error.get("msg")
    elif error:
        message = message or str(error)

    has_content = bool(data.get("references"))
    request_id = (
        data.get("request_id")
        or data.get("requestId")
        or data.get("request_Id")
    )

    text = ""
    if code is not None and str(code).strip() not in ("", "0", "200"):
        text = "code {}: {}".format(code, message or "未知错误")
    elif message and not has_content:
        text = str(message)

    if not text:
        return ""
    if request_id:
        text += "（requestId: {}）".format(request_id)
    return text[:_MAX_ERROR_CHARS]


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:  # noqa: BLE001 - error body is best-effort
        raw = b""

    data = _decode_json(raw)
    if isinstance(data, dict):
        detail = _api_error(data)
        if detail:
            return detail

    reason = str(exc.reason or "").strip()
    return reason or "未知错误"


def _iter_references(value: Any):
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item
    elif isinstance(value, dict):
        if "url" in value or "title" in value:
            yield value
            return
        for item in value.values():
            if isinstance(item, dict):
                yield item


def _extract_results(data: dict[str, Any]) -> list[_SearchResult]:
    results: list[_SearchResult] = []
    seen: set[str] = set()

    for item in _iter_references(data.get("references")):
        url = str(item.get("url") or "").strip()
        if not url:
            continue

        ref_type = str(item.get("type") or "").strip().lower()
        if ref_type and ref_type != "web":
            continue

        title = str(item.get("title") or item.get("web_anchor") or "").strip()
        if not title:
            title = url

        snippet = _clean_snippet(
            str(item.get("snippet") or item.get("content") or "")
        )
        if len(snippet) > _MAX_SNIPPET_CHARS:
            snippet = snippet[:_MAX_SNIPPET_CHARS].rstrip() + "..."

        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(
            _SearchResult(
                title=title,
                url=url,
                snippet=snippet,
                website=str(item.get("website") or "").strip(),
                date=str(item.get("date") or "").strip(),
            )
        )
        if len(results) >= _MAX_RESULTS:
            break

    return results


def _format_result(
    query: str,
    results: list[_SearchResult],
    truncated: bool,
) -> str:
    parts = ["搜索关键词: " + query]
    if truncated:
        parts.append(
            "注意: 查询超过 API 的 72 字符限制，已截断后搜索。"
        )

    if not results:
        parts.append("搜索结果: （API 未返回搜索结果）")
        return "\n\n".join(parts)

    lines = ["搜索结果:"]
    for index, item in enumerate(results, 1):
        lines.append("{}. [{}]({})".format(index, item.title, item.url))
        meta = []
        if item.website:
            meta.append("站点: " + item.website)
        if item.date:
            meta.append("日期: " + item.date)
        if meta:
            lines.append("   " + " | ".join(meta))
        if item.snippet:
            lines.append("   摘要: " + item.snippet)
    parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _request_payload(query: str) -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": query}],
        "search_source": _SEARCH_SOURCE,
        "edition": "standard",
        "resource_type_filter": [{"type": "web", "top_k": _MAX_RESULTS}],
    }


def search_web(query: str, config: SearchConfig | None = None) -> str:
    query, truncated = _prepare_query(query)
    if not query:
        return "搜索关键词不能为空"

    if config is None:
        config = load_search_config()
    if not config.api_key:
        return _missing_config_message(config)

    try:
        parsed = urlparse(config.base_url)
    except ValueError as exc:
        return "搜索 API 地址无效: {} ({})".format(config.base_url, exc)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "搜索 API 地址无效: " + config.base_url

    payload = _request_payload(query)
    try:
        request = urllib.request.Request(
            config.base_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + config.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "wAgent/1.0",
            },
            method="POST",
        )
    except (TypeError, ValueError) as exc:
        return "搜索 API 请求构造失败: {}".format(exc)

    try:
        with urllib.request.urlopen(request, timeout=_SEARCH_TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = _http_error_detail(exc)
        return _with_permission_hint(
            "搜索 API 请求失败（HTTP {}）: {}".format(exc.code, detail)
        )
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return "搜索 API 请求超时（超过 {} 秒）".format(_SEARCH_TIMEOUT)
        return "搜索 API 网络请求失败: {}".format(reason)
    except (TimeoutError, socket.timeout):
        return "搜索 API 请求超时（超过 {} 秒）".format(_SEARCH_TIMEOUT)
    except OSError as exc:
        return "搜索 API 网络请求失败: {}".format(exc)
    except Exception as exc:  # noqa: BLE001 - keep failures readable to the LLM
        return "搜索 API 请求失败: {}".format(exc)

    data = _decode_json(raw)
    if not isinstance(data, dict):
        return "搜索 API 返回了无法解析的响应内容"

    error = _api_error(data)
    if error:
        return _with_permission_hint("搜索 API 返回错误: " + error)

    results = _extract_results(data)
    if not results:
        return "搜索 API 返回成功，但未包含搜索结果: " + query

    return _format_result(query, results, truncated)


def build_search_tools(config: SearchConfig | None = None) -> tuple[ToolSpec, ...]:
    def handler(query: str) -> str:
        return search_web(query, config=config)

    return (
        ToolSpec(
            name="searchweb",
            description=(
                "使用百度搜索获取互联网上的最新信息，"
                "返回搜索结果的摘要、标题和 URL。"
                "适用于新闻、实时动态、当前事件或需要联网核实的问题。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或需要联网回答的问题（建议不超过 72 字符）",
                    }
                },
                "required": ["query"],
            },
            handler=handler,
        ),
    )

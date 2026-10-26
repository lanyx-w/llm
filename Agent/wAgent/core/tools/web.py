"""Web tools: fetch a page with curl and extract its main content as Markdown."""

from __future__ import annotations

import locale
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

from .base import ToolSpec

_CONNECT_TIMEOUT = 10
_REQUEST_TIMEOUT = 30
_MAX_HTML_BYTES = 10 * 1024 * 1024
_MAX_OUTPUT_CHARS = 30000
_MAX_ERROR_CHARS = 500
_MIN_CONTENT_CHARS = 100
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", locale.getpreferredencoding(False), "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _validate_url(url: str) -> str | None:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return value


def _fetch_html(url: str) -> tuple[bytes | None, str | None]:
    curl = shutil.which("curl")
    if not curl:
        return None, "未找到 curl 命令，请先安装 curl 并加入 PATH"

    command = [
        curl,
        "-sS",
        "-L",
        "--fail",
        "--compressed",
        "--max-redirs",
        "5",
        "--max-filesize",
        str(_MAX_HTML_BYTES),
        "--connect-timeout",
        str(_CONNECT_TIMEOUT),
        "--max-time",
        str(_REQUEST_TIMEOUT),
        "-A",
        _USER_AGENT,
        "-H",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H",
        "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        url,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=_REQUEST_TIMEOUT + 5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "访问网页超时（超过 {} 秒）: {}".format(_REQUEST_TIMEOUT, url)
    except FileNotFoundError:
        return None, "未找到 curl 命令，请先安装 curl 并加入 PATH"
    except OSError as exc:
        return None, "调用 curl 失败: {}".format(exc)

    if result.returncode != 0:
        detail = _decode(result.stderr).strip()[:_MAX_ERROR_CHARS]
        if result.returncode == 28:
            message = "访问网页超时: " + url
        elif result.returncode == 63:
            return None, "网页内容过大（超过 {} MB）: {}".format(
                _MAX_HTML_BYTES // (1024 * 1024), url
            )
        else:
            message = "网页访问失败（curl 退出码 {}）: {}".format(
                result.returncode, url
            )
        if detail:
            message += "\n详情: " + detail
        return None, message

    if not result.stdout:
        return None, "网页返回了空内容: " + url
    if len(result.stdout) > _MAX_HTML_BYTES:
        return None, "网页内容过大（超过 {} MB）: {}".format(
            _MAX_HTML_BYTES // (1024 * 1024), url
        )
    if b"\x00" in result.stdout[:4096]:
        return None, "目标地址返回的是二进制内容，不是 HTML 网页: " + url
    return result.stdout, None


def _find_browser() -> str | None:
    candidates: list[str] = []
    for name in (
        "msedge",
        "chrome",
        "chromium",
        "google-chrome",
        "microsoft-edge",
        "chromium-browser",
    ):
        path = shutil.which(name)
        if path:
            candidates.append(path)

    if os.name == "nt":
        roots = (
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("ProgramFiles"),
            os.environ.get("LOCALAPPDATA"),
        )
        relative_paths = (
            ("Microsoft", "Edge", "Application", "msedge.exe"),
            ("Google", "Chrome", "Application", "chrome.exe"),
            ("Chromium", "Application", "chrome.exe"),
        )
        for root in roots:
            if not root:
                continue
            for relative in relative_paths:
                candidates.append(os.path.join(root, *relative))
    elif sys.platform == "darwin":
        candidates.extend(
            (
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            )
        )
    else:
        candidates.extend(
            (
                "/usr/bin/microsoft-edge",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            )
        )

    seen: set[str] = set()
    for path in candidates:
        normalized = os.path.normcase(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(path):
            return path
    return None


def _fetch_rendered_html(url: str) -> tuple[bytes | None, str | None]:
    browser = _find_browser()
    if not browser:
        return None, "未找到可用的无头浏览器（Edge/Chrome/Chromium）"

    profile_dir = tempfile.mkdtemp(prefix="wagent-browser-")
    command = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        "--user-data-dir=" + profile_dir,
        "--virtual-time-budget=8000",
        "--dump-dom",
        url,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=_REQUEST_TIMEOUT + 20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "无头浏览器渲染网页超时: " + url
    except OSError as exc:
        return None, "启动无头浏览器失败: {}".format(exc)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    if not result.stdout:
        detail = _decode(result.stderr).strip()[:_MAX_ERROR_CHARS]
        message = "无头浏览器未返回网页内容: " + url
        if detail:
            message += "\n详情: " + detail
        return None, message
    if len(result.stdout) > _MAX_HTML_BYTES:
        return None, "渲染后的网页内容过大（超过 {} MB）: {}".format(
            _MAX_HTML_BYTES // (1024 * 1024), url
        )
    return result.stdout, None


def _extract_markdown(html: bytes, url: str) -> tuple[str | None, str | None]:
    try:
        import trafilatura
    except ImportError:
        return None, (
            "缺少 trafilatura 依赖（当前 Python: {}）。请运行: \"{}\" -m pip install trafilatura"
        ).format(sys.executable, sys.executable)

    try:
        markdown = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_links=True,
            include_images=False,
            include_formatting=True,
            favor_recall=False,
        )
    except Exception as exc:  # noqa: BLE001 - surface parser errors to the LLM
        return None, "HTML 解析失败: {}".format(exc)

    if not markdown or not markdown.strip():
        return None, (
            "无法从网页提取正文（页面可能由 JavaScript 动态渲染、需要登录或内容为空）: "
            + url
        )
    return markdown.strip(), None


def _fallback_failure(primary: str, fallback: str | None) -> str:
    if fallback:
        return primary + "\n\n已尝试使用无头浏览器渲染，但仍失败: " + fallback
    return primary


def fetch_web(url: str) -> str:
    value = _validate_url(url)
    if value is None:
        return "无效的网页 URL（仅支持 http/https 地址）: " + str(url or "")

    html, error = _fetch_html(value)
    if error:
        return error

    markdown, error = _extract_markdown(html, value)
    if error or markdown is None or len(markdown) < _MIN_CONTENT_CHARS:
        rendered, render_error = _fetch_rendered_html(value)
        if rendered is not None:
            rendered_markdown, rendered_error = _extract_markdown(rendered, value)
            if rendered_markdown is not None and (
                markdown is None or len(rendered_markdown) > len(markdown)
            ):
                markdown = rendered_markdown
                error = None
            elif markdown is None:
                error = _fallback_failure(error, rendered_error)
        elif markdown is None:
            error = _fallback_failure(error, render_error)

    if error:
        return error

    if len(markdown) > _MAX_OUTPUT_CHARS:
        markdown = (
            markdown[:_MAX_OUTPUT_CHARS].rstrip()
            + "\n\n...（正文过长，已截断）"
        )

    return "URL: {}\n\n{}".format(value, markdown)


WEB_TOOLS = (
    ToolSpec(
        name="fetchWeb",
        description=(
            "获取指定网页的主要内容并转换为 Markdown。"
            "保留标题、段落、列表、表格和链接，去除导航栏、广告、页脚等无关内容；"
            "仅支持 http/https 网页，超长正文会被截断。"
            "静态抓取无法提取正文或正文过短时，会自动尝试用本机 Edge/Chrome 无头浏览器渲染页面。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取内容的网页 URL，必须以 http:// 或 https:// 开头",
                }
            },
            "required": ["url"],
        },
        handler=fetch_web,
    ),
)

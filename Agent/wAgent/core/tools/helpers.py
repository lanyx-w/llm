"""Shared filesystem/text helpers used by tool implementations."""

from __future__ import annotations

import locale
import mimetypes
import os
import subprocess

TEXT_EXTENSIONS = {
    ".bat", ".c", ".cfg", ".conf", ".cpp", ".cs", ".css", ".csv", ".go",
    ".h", ".hpp", ".htm", ".html", ".ini", ".java", ".js", ".json", ".jsx",
    ".log", ".lua", ".md", ".php", ".properties", ".ps1", ".py", ".rb",
    ".rst", ".rs", ".sh", ".sql", ".svg", ".tex", ".toml", ".ts", ".tsx",
    ".txt", ".vue", ".xml", ".yaml", ".yml",
}

BINARY_EXTENSIONS = {
    ".7z", ".avi", ".bin", ".bmp", ".dll", ".doc", ".docx", ".exe", ".gif",
    ".gz", ".ico", ".jpeg", ".jpg", ".mkv", ".mov", ".mp3", ".mp4", ".pdf",
    ".png", ".ppt", ".pptx", ".rar", ".so", ".tar", ".wav", ".webp", ".xls",
    ".xlsx", ".zip",
}


def run_command(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True)
    data = result.stdout
    if result.returncode != 0 and not data:
        data = result.stderr

    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return data.decode(encoding).strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace").strip()


def resolve_path(path: str) -> str:
    path = os.path.expanduser(str(path))
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    return os.path.abspath(path)


def looks_like_text(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return False
    if ext in TEXT_EXTENSIONS:
        return True

    mime, _ = mimetypes.guess_type(path)
    if mime and (
        mime.startswith("text/")
        or mime in (
            "application/json",
            "application/xml",
            "application/javascript",
            "application/x-yaml",
        )
    ):
        return True

    try:
        with open(path, "rb") as f:
            sample = f.read(4096)
    except OSError:
        return False

    if b"\x00" in sample:
        return False
    if not sample:
        return True

    control_count = sum(1 for byte in sample if byte < 9 or 13 < byte < 32)
    return control_count / len(sample) < 0.3


def read_text(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()

    encodings = ["utf-8-sig", "gbk", locale.getpreferredencoding(False), "utf-8"]
    tried: set[str] = set()
    for encoding in encodings:
        if not encoding or encoding.lower() in tried:
            continue
        tried.add(encoding.lower())
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")

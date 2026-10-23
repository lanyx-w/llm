"""LLM configuration loading.

The core layer intentionally knows nothing about any UI. Configuration is read
from an INI file so every front-end (TUI, Web, Desktop) shares the same source.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_ENV_VAR = "WAGENT_CONFIG"
DEFAULT_CONFIG_NAME = "config.ini"


class ConfigError(RuntimeError):
    """Raised when the agent configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Immutable LLM connection settings."""

    base_url: str
    model_name: str
    api_key: str

    @classmethod
    def from_ini(cls, path: str | Path) -> "LLMConfig":
        return _read_ini(Path(path))


def load_config(path: str | Path | None = None) -> LLMConfig:
    """Load configuration from an explicit path or the default search order.

    Search order:
    1. ``path`` argument, when provided;
    2. the ``WAGENT_CONFIG`` environment variable;
    3. ``./config.ini`` relative to the current working directory;
    4. the project root (the directory containing ``core`` and ``tui``).
    """

    candidates = list(_candidate_paths(path))
    for candidate in candidates:
        if candidate.is_file():
            return _read_ini(candidate)

    searched = "\n".join(f"  - {candidate}" for candidate in candidates)
    raise ConfigError(
        "未找到 config.ini。请复制 config.example.ini 为 config.ini 并填写 API Key。\n"
        f"已查找以下位置：\n{searched}"
    )


def _candidate_paths(path: str | Path | None):
    if path is not None:
        yield Path(path).expanduser()
        return

    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        yield Path(env_path).expanduser()

    yield Path.cwd() / DEFAULT_CONFIG_NAME
    yield PROJECT_ROOT / DEFAULT_CONFIG_NAME


def _read_ini(path: Path) -> LLMConfig:
    parser = configparser.ConfigParser()
    try:
        read_ok = parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        raise ConfigError(f"读取配置文件失败: {path} ({exc})") from exc

    if not read_ok:
        raise ConfigError(f"无法读取配置文件: {path}")

    if not parser.has_section("llm"):
        raise ConfigError(f"配置文件 {path} 缺少 [llm] 段")

    section = parser["llm"]
    values = {
        "base_url": section.get("base_url", "").strip(),
        "model_name": section.get("model_name", "").strip(),
        "api_key": section.get("api_key", "").strip(),
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ConfigError(
            f"配置文件 {path} 的 [llm] 段缺少字段: {', '.join(missing)}"
        )

    return LLMConfig(**values)

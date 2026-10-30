"""Agent Skills discovery and on-demand loading.

Skills live under ``<project>/.agents/skills/<skill>/SKILL.md``. Only the YAML
frontmatter (``name`` and ``description``) is read during discovery; the rest of
the file is loaded lazily through the ``loadSkill`` tool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SKILLS_RELATIVE_PATH = Path(".agents") / "skills"
SKILL_ENTRY_NAME = "SKILL.md"
MAX_FRONTMATTER_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class Skill:
    """Metadata for one discovered skill."""

    name: str
    description: str
    directory: Path
    entry_file: Path


class SkillRegistry:
    """Ordered collection of skills addressable by name."""

    def __init__(
        self,
        skills: tuple[Skill, ...] = (),
        project_root: str | Path | None = None,
    ) -> None:
        self._project_root = _resolve_path(project_root or Path.cwd())
        self._skills: dict[str, Skill] = {}
        for skill in skills:
            if skill.name not in self._skills:
                self._skills[skill.name] = skill

    @classmethod
    def discover(cls, project_root: str | Path | None = None) -> "SkillRegistry":
        """Scan ``<project_root>/.agents/skills`` for skill directories."""
        root = _resolve_path(project_root or Path.cwd())
        skills_root = root / SKILLS_RELATIVE_PATH
        skills: list[Skill] = []

        if skills_root.is_dir():
            try:
                children = sorted(
                    skills_root.iterdir(),
                    key=lambda path: path.name.casefold(),
                )
            except OSError:
                children = []

            for child in children:
                if not child.is_dir():
                    continue

                entry = child / SKILL_ENTRY_NAME
                if not entry.is_file():
                    continue

                metadata = _read_frontmatter(entry)
                if metadata is None:
                    continue

                name = metadata.get("name", "").strip()
                description = metadata.get("description", "").strip()
                if not name or not description:
                    continue

                directory = _resolve_path(child)
                entry_file = _resolve_path(entry)
                if not _is_relative_to(entry_file, directory):
                    continue

                skills.append(
                    Skill(
                        name=name,
                        description=description,
                        directory=directory,
                        entry_file=entry_file,
                    )
                )

        return cls(tuple(skills), project_root=root)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(str(name).strip())

    def prompt_section(self) -> str:
        """Render the skill list for the system prompt."""
        if not self._skills:
            return ""

        lines = ["You have access to the following skills:"]
        for skill in self._skills.values():
            description = " ".join(skill.description.split())
            lines.append(f"{skill.name}: {description}")
        lines.append(
            "Use the loadSkill tool to load the full instructions of a skill "
            "when needed. You can also load additional files referenced by a skill."
        )
        return "\n".join(lines)

    def load(self, name: str, filename: str | None = None) -> str:
        """Return the skill entry file or one of its attachment files."""
        skill = self.get(name)
        if skill is None:
            available = ", ".join(self._skills) or "（无）"
            return f"未找到技能: {name}\n可用技能: {available}"

        if filename is None or not str(filename).strip():
            return _read_file(skill.entry_file)

        resolved = _resolve_attachment(
            skill,
            str(filename).strip(),
            self._project_root,
        )
        if isinstance(resolved, str):
            return resolved
        return _read_file(resolved)


def build_skill_tools(registry: SkillRegistry) -> tuple[ToolSpec, ...]:
    """Return the ``loadSkill`` tool bound to ``registry``."""
    from .tools.base import ToolSpec

    return (
        ToolSpec(
            name="loadSkill",
            description=(
                "按需加载某个技能（Skill）的完整说明，或读取该技能目录下的附件文件。"
                "只提供 name 时返回 SKILL.md 全文；同时提供 filename 时读取指定附件。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名称，必须是系统提示中列出的可用技能之一",
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "可选。技能附件的路径或文件名，支持相对于技能目录的路径、"
                            "项目相对路径和绝对路径；省略时加载 SKILL.md 全文"
                        ),
                    },
                },
                "required": ["name"],
            },
            handler=registry.load,
        ),
    )


def build_system_prompt(base_prompt: str, registry: SkillRegistry) -> str:
    """Append the available-skill section to ``base_prompt``."""
    section = registry.prompt_section()
    if not section:
        return base_prompt
    if not base_prompt:
        return section
    return base_prompt.rstrip() + "\n\n" + section


def _resolve_attachment(
    skill: Skill,
    filename: str,
    project_root: Path,
) -> Path | str:
    raw = Path(os.path.expanduser(filename))
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(skill.directory / raw)
        candidates.append(project_root / raw)

    denied = False
    for candidate in candidates:
        resolved = _resolve_path(candidate)
        if not _is_relative_to(resolved, skill.directory):
            if resolved.exists() or raw.is_absolute():
                denied = True
            continue
        if resolved.is_file():
            return resolved

    if _is_bare_filename(filename):
        matches = _find_by_name(skill.directory, filename)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            lines = ["找到多个同名文件，请在 filename 中指定具体路径："]
            for match in matches:
                lines.append(f"- {_relative_name(match, skill.directory)}")
            return "\n".join(lines)

    if denied:
        return f"不允许读取技能目录之外的文件: {filename}"
    return f"未在技能 {skill.name} 中找到文件: {filename}"


def _find_by_name(directory: Path, filename: str) -> list[Path]:
    matches: list[Path] = []
    seen: set[str] = set()
    for root, _dirs, files in os.walk(directory, followlinks=False):
        for name in files:
            if not _names_equal(name, filename):
                continue
            resolved = _resolve_path(Path(root) / name)
            if not _is_relative_to(resolved, directory):
                continue
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            matches.append(resolved)
    matches.sort(key=lambda path: str(path).casefold())
    return matches


def _relative_name(path: Path, directory: Path) -> str:
    try:
        return path.relative_to(directory).as_posix()
    except ValueError:
        return str(path)


def _is_bare_filename(filename: str) -> bool:
    return filename not in {".", ".."} and Path(filename).name == filename


def _names_equal(left: str, right: str) -> bool:
    return os.path.normcase(left) == os.path.normcase(right)


def _resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        common = os.path.commonpath(
            [os.path.normcase(str(path)), os.path.normcase(str(base))]
        )
    except ValueError:
        return False
    return common == os.path.normcase(str(base))


def _read_file(path: Path) -> str:
    from .tools.helpers import looks_like_text, read_text

    if not path.is_file():
        return f"文件不存在: {path}"
    if not looks_like_text(str(path)):
        return f"不支持读取非文本文件: {path}"
    try:
        return read_text(str(path))
    except OSError as exc:
        return f"读取文件失败: {exc}"


def _read_frontmatter(path: Path) -> dict[str, str] | None:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            first = handle.readline()
            if first.strip() != "---":
                return None

            lines = [first.rstrip("\r\n")]
            total = len(first)
            while True:
                line = handle.readline()
                if not line:
                    return None
                total += len(line)
                if total > MAX_FRONTMATTER_BYTES:
                    return None
                lines.append(line.rstrip("\r\n"))
                if line.strip() in {"---", "..."}:
                    break
    except OSError:
        return None

    return _parse_frontmatter(lines[1:-1])


def _parse_frontmatter(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or raw[0].isspace():
            index += 1
            continue

        key, separator, value = raw.partition(":")
        if not separator:
            index += 1
            continue

        key = key.strip()
        value = value.strip()
        if value[:1] in {"|", ">"}:
            value, index = _parse_block_scalar(value, lines, index + 1)
        else:
            value = _parse_scalar(value)
            index += 1

        if key in {"name", "description"}:
            values[key] = value
    return values


def _parse_block_scalar(
    indicator: str,
    lines: list[str],
    start: int,
) -> tuple[str, int]:
    block: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line[0].isspace():
            block.append(line)
            index += 1
            continue
        break

    while block and not block[-1].strip():
        block.pop()

    indents = [
        len(line) - len(line.lstrip())
        for line in block
        if line.strip()
    ]
    indent = min(indents, default=0)
    content = [line[indent:] if line.strip() else "" for line in block]

    if indicator.startswith(">"):
        folded: list[str] = []
        paragraph: list[str] = []
        for line in content:
            if not line:
                if paragraph:
                    folded.append(" ".join(paragraph))
                    paragraph = []
                folded.append("")
            else:
                paragraph.append(line.strip())
        if paragraph:
            folded.append(" ".join(paragraph))
        text = "\n".join(folded)
    else:
        text = "\n".join(content)

    return text.strip(), index


def _parse_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        inner = value[1:-1]
        if quote == '"':
            return (
                inner.replace('\\"', '"')
                .replace("\\n", "\n")
                .replace("\\\\", "\\")
            )
        return inner.replace("''", "'")

    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
    return value.strip()

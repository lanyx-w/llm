"""Filesystem tools: read, write, create, delete, rename."""

from __future__ import annotations

import mimetypes
import os
import shutil

from .base import ToolSpec
from .helpers import looks_like_text, read_text, resolve_path


def list_directory(path: str = ".") -> str:
    target = resolve_path(path)
    if not os.path.exists(target):
        return "目录不存在: " + target
    if not os.path.isdir(target):
        return "路径不是目录: " + target

    try:
        entries = list(os.scandir(target))
    except OSError as exc:
        return "无法列出目录: " + str(exc)

    entries.sort(key=lambda entry: (not entry.is_dir(), entry.name.lower()))
    lines = ["目录: {}（共 {} 项）".format(target, len(entries))]

    if not entries:
        lines.append("（空目录）")
        return "\n".join(lines)

    for entry in entries:
        try:
            if entry.is_dir():
                lines.append("[目录] " + entry.name)
            else:
                size = entry.stat().st_size
                lines.append("[文件] {}（{} 字节）".format(entry.name, size))
        except OSError:
            lines.append("[未知] " + entry.name)
    return "\n".join(lines)


def get_file_type(path: str) -> str:
    target = resolve_path(path)
    if not os.path.exists(target):
        return "路径不存在: " + target
    if os.path.isdir(target):
        return "路径: {}\n类型: 目录".format(target)

    ext = os.path.splitext(target)[1].lower() or "（无扩展名）"
    mime, _ = mimetypes.guess_type(target)
    if not mime:
        mime = "未知"
    is_text = looks_like_text(target)

    return "路径: {}\n类型: 文件\n扩展名: {}\nMIME 类型: {}\n纯文本文件: {}".format(
        target, ext, mime, "是" if is_text else "否"
    )


def read_text_file(path: str) -> str:
    target = resolve_path(path)
    if not os.path.exists(target):
        return "文件不存在: " + target
    if os.path.isdir(target):
        return "路径是目录，不是文件: " + target
    if not looks_like_text(target):
        return "不支持读取该文件，仅支持纯文本格式文件: " + target

    try:
        return read_text(target)
    except OSError as exc:
        return "读取文件失败: " + str(exc)


def create_file(directory: str, filename: str, content: str = "") -> str:
    directory_path = resolve_path(directory)
    if not os.path.isdir(directory_path):
        return "目录不存在: " + directory_path

    filename = str(filename).strip()
    if not filename:
        return "文件名不能为空"
    if os.path.basename(filename) != filename:
        return "filename 只能包含文件名，不能包含路径"

    target = os.path.join(directory_path, filename)
    if os.path.exists(target):
        return "文件已存在: " + target

    try:
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(content or "")
    except OSError as exc:
        return "创建文件失败: " + str(exc)
    return "文件创建成功: " + target


def edit_file(
    path: str,
    content: str,
    mode: str = "overwrite",
    old_text: str | None = None,
) -> str:
    target = resolve_path(path)
    if not os.path.exists(target):
        return "文件不存在: " + target
    if os.path.isdir(target):
        return "路径是目录，不是文件: " + target
    if not looks_like_text(target):
        return "不支持编辑该文件，仅支持纯文本格式文件: " + target

    try:
        original = read_text(target)
    except OSError as exc:
        return "读取文件失败: " + str(exc)

    mode = (mode or "overwrite").lower()
    try:
        if mode == "append":
            with open(target, "a", encoding="utf-8", newline="") as f:
                f.write(content or "")
            return "内容已追加到文件: " + target

        if mode == "replace":
            if old_text is None or old_text == "":
                return "replace 模式下必须提供 old_text"
            if old_text not in original:
                return "未在文件中找到要替换的文本: " + target
            updated = original.replace(old_text, content or "", 1)
        elif mode == "overwrite":
            updated = content or ""
        else:
            return "不支持的编辑方式: " + mode

        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write(updated)
    except OSError as exc:
        return "编辑文件失败: " + str(exc)

    return "文件编辑成功: " + target


def create_directory(path: str) -> str:
    target = resolve_path(path)
    if os.path.exists(target):
        if os.path.isdir(target):
            return "目录已存在: " + target
        return "同名文件已存在，无法创建目录: " + target

    try:
        os.makedirs(target)
    except OSError as exc:
        return "创建目录失败: " + str(exc)
    return "目录创建成功: " + target


def delete_directory(path: str) -> str:
    target = resolve_path(path)
    if not os.path.exists(target):
        return "目录不存在: " + target
    if not os.path.isdir(target):
        return "路径不是目录: " + target

    normalized = os.path.normcase(target)
    cwd = os.path.normcase(os.path.abspath(os.getcwd()))
    if os.path.dirname(normalized) == normalized:
        return "不允许删除根目录: " + target
    if cwd == normalized or cwd.startswith(normalized + os.sep):
        return "不允许删除当前工作目录或其上级目录: " + target

    try:
        shutil.rmtree(target)
    except OSError as exc:
        return "删除目录失败: " + str(exc)
    return "目录删除成功: " + target


def delete_file(path: str) -> str:
    target = resolve_path(path)
    if not os.path.exists(target):
        return "文件不存在: " + target
    if os.path.isdir(target):
        return "路径是目录，请使用 deleteDirectory 删除: " + target

    try:
        os.remove(target)
    except OSError as exc:
        return "删除文件失败: " + str(exc)
    return "文件删除成功: " + target


def rename_file_or_directory(path: str, new_name: str) -> str:
    target = resolve_path(path)
    if not os.path.exists(target):
        return "路径不存在: " + target
    if os.path.dirname(target) == target:
        return "不允许重命名根目录: " + target

    new_name = str(new_name).strip()
    if not new_name:
        return "新名称不能为空"
    if os.path.basename(new_name) != new_name:
        return "new_name 只能包含新名称，不能包含路径"

    destination = os.path.join(os.path.dirname(target), new_name)
    if os.path.normcase(destination) == os.path.normcase(target):
        return "新名称与原名称相同: " + target
    if os.path.exists(destination):
        return "目标路径已存在: " + destination

    try:
        os.rename(target, destination)
    except OSError as exc:
        return "重命名失败: " + str(exc)
    return "重命名成功: {} -> {}".format(target, destination)


FILESYSTEM_TOOLS = (
    ToolSpec(
        name="listDirectory",
        description="列出指定目录下的所有文件和子目录",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要列出的目录路径；相对路径基于当前工作目录，省略时使用当前工作目录",
                }
            },
            "required": [],
        },
        handler=list_directory,
    ),
    ToolSpec(
        name="getFileType",
        description="获取指定文件的类型，包括扩展名、MIME 类型以及是否为纯文本文件",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要检查的文件路径"}
            },
            "required": ["path"],
        },
        handler=get_file_type,
    ),
    ToolSpec(
        name="readTextFile",
        description="读取指定纯文本文件的内容；不支持图片、压缩包、可执行文件等二进制文件",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要读取的纯文本文件路径"}
            },
            "required": ["path"],
        },
        handler=read_text_file,
    ),
    ToolSpec(
        name="createFile",
        description="在指定目录下创建新文件；如果文件已存在则不会覆盖",
        parameters={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": '文件所在目录，必须已经存在；使用 "." 表示当前工作目录',
                },
                "filename": {
                    "type": "string",
                    "description": "新文件名（包含扩展名，不要包含路径）",
                },
                "content": {
                    "type": "string",
                    "description": "文件初始内容，默认为空字符串",
                },
            },
            "required": ["directory", "filename"],
        },
        handler=create_file,
    ),
    ToolSpec(
        name="editFile",
        description="编辑指定纯文本文件的内容，支持整体覆盖、追加或替换指定文本",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要编辑的纯文本文件路径"},
                "content": {
                    "type": "string",
                    "description": "新内容；overwrite 模式下为完整的新内容，append 模式下为追加内容，replace 模式下为替换后的文本",
                },
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append", "replace"],
                    "description": "编辑方式：overwrite 覆盖整个文件，append 追加到文件末尾，replace 替换 old_text；默认 overwrite",
                },
                "old_text": {
                    "type": "string",
                    "description": "replace 模式下要被替换的原文本",
                },
            },
            "required": ["path", "content"],
        },
        handler=edit_file,
    ),
    ToolSpec(
        name="createDirectory",
        description="创建新目录，支持一次创建多级目录",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要创建的目录路径"}
            },
            "required": ["path"],
        },
        handler=create_directory,
    ),
    ToolSpec(
        name="deleteDirectory",
        description="删除指定目录，包括非空目录及其中的所有文件和子目录",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的目录路径"}
            },
            "required": ["path"],
        },
        handler=delete_directory,
    ),
    ToolSpec(
        name="deleteFile",
        description="删除指定文件",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的文件路径"}
            },
            "required": ["path"],
        },
        handler=delete_file,
    ),
    ToolSpec(
        name="renameFileOrDirectory",
        description="重命名文件或目录，新名称必须与原路径位于同一目录下",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要重命名的文件或目录路径"},
                "new_name": {
                    "type": "string",
                    "description": "新的名称（不要包含路径）",
                },
            },
            "required": ["path", "new_name"],
        },
        handler=rename_file_or_directory,
    ),
)

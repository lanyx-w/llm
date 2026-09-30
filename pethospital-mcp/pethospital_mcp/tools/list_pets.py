"""list_pets 工具：ListPets 参数模型 + 处理器 + 结果渲染/截断。"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from ..petapi import PetApi, UpstreamError

# 数据 JSON 摘要的最大字符数，超长截断并提示
_JSON_LIMIT = 20_000
# 总花费数字越大时列表越长，单条摘要也尽量精简
_SLIM_KEYS = (
    "id",
    "name",
    "species",
    "breed",
    "gender",
    "ageMonths",
    "ownerName",
    "ownerPhone",
    "doctor",
    "disease",
    "status",
    "chipNo",
    "allergy",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
)


class ListPets(BaseModel):
    """list_pets 的参数模型：字段与工具入参一一对应（描述随字段走）。"""

    q: str | None = Field(
        default=None,
        description="跨字段全文检索（空格分词 AND，含病历全文）",
    )
    name: str | None = Field(default=None, description="按宠物姓名精确筛选")
    ownerName: str | None = Field(default=None, description="按主人姓名精确筛选")
    ownerPhone: str | None = Field(default=None, description="按主人电话精确筛选")
    species: str | None = Field(default=None, description="按种类筛选，如：犬 / 猫")
    doctor: str | None = Field(default=None, description="按主治医生精确筛选")
    disease: str | None = Field(default=None, description="按疾病精确筛选")
    status: str | None = Field(
        default=None,
        description="按就诊状态筛选，如：待就诊 / 就诊中 / 住院中 / 已康复 / 慢性病随访",
    )
    # min/max 为总花费区间；字段名刻意与上游参数一致
    min: float | None = Field(default=None, description="按总花费下限（>=）筛选")
    max: float | None = Field(default=None, description="按总花费上限（<=）筛选")
    sortBy: str | None = Field(default=None, description="排序字段，如 totalCost / name / visitCount")
    order: Literal["asc", "desc"] | None = Field(default=None, description="排序方向 asc|desc")
    page: int = Field(default=1, ge=1, description="页码，从 1 开始，默认 1")
    pageSize: int = Field(default=10, ge=1, le=100, description="每页条数，默认 10，上限 100")


def _build_query(params: ListPets) -> dict[str, Any]:
    """把参数模型转成上游查询串；只发送用户显式给出的条件。"""
    query: dict[str, Any] = {}
    for key, value in params.model_dump().items():
        if value is None:
            continue
        if key in ("min", "max") and isinstance(value, float) and value.is_integer():
            value = int(value)
        query[key] = value
    # 默认页/页大小总是显式发送，让上游遵守 MCP 契约而非上游自身的默认值
    query.setdefault("page", params.page)
    query.setdefault("pageSize", params.pageSize)
    return query


def _fmt_item(item: dict[str, Any]) -> str:
    """把单只宠物渲染成一行中文摘要。"""
    parts = [item.get("id", ""), item.get("name", "")]
    if item.get("species"):
        parts.append(f"({item['species']})")
    for label, key in (
        ("主人", "ownerName"),
        ("医生", "doctor"),
        ("疾病", "disease"),
        ("状态", "status"),
    ):
        if item.get(key):
            parts.append(f"{label}：{item[key]}")
    cost = item.get("totalCost", 0)
    parts.append(f"总花费 ¥{cost:,.2f}")
    parts.append(f"就诊 {item.get('visitCount', 0)} 次")
    return "  ".join(parts)


def _slim_item(item: dict[str, Any]) -> dict[str, Any]:
    """去掉病历/消费明细等大字段，只留摘要字段（供 JSON 摘要）。"""
    slim = {key: item[key] for key in _SLIM_KEYS if key in item}
    slim["recordCount"] = len(item.get("records") or [])
    slim["chargeCount"] = len(item.get("charges") or [])
    return slim


def render_result(data: dict[str, Any], page_size: int) -> str:
    """渲染中文可读摘要 + 数据 JSON 摘要；超长结果截断并提示。"""
    items = data.get("items") or []
    total = data.get("total", 0)
    page = data.get("page", 1)
    total_pages = data.get("totalPages")

    lines = [f"共命中 {total} 条，当前第 {page} 页 / 共 {total_pages} 页（本页 {len(items)} 条）。", ""]
    lines.append("宠物列表（ID + 名字）：")
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {_fmt_item(item)}")

    if total > len(items):
        lines.append("")
        lines.append(f"已有 {total} 条命中，建议缩小筛选或翻页查看。")

    lines.extend(["", "数据 JSON 摘要："])
    slim: dict[str, Any] = {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "items": [_slim_item(item) for item in items],
    }
    js = json.dumps(slim, ensure_ascii=False, indent=2)
    if len(js) > _JSON_LIMIT:
        js = js[:_JSON_LIMIT] + f"\n...(共 {total} 条，结果过长已截断，建议缩小筛选或翻页)"
    lines.append(js)
    return "\n".join(lines)


def make_handler(api: PetApi):
    """创建 list_pets 处理器：参数为扁平签名，SDK 据此生成 inputSchema 并校验。

    处理器内部把已校验参数交给 ListPets 模型整理后调用上游。
    """

    async def handler(
        q: Annotated[str | None, Field(description="跨字段全文检索（空格分词 AND，含病历全文）")] = None,
        name: Annotated[str | None, Field(description="按宠物姓名精确筛选")] = None,
        ownerName: Annotated[str | None, Field(description="按主人姓名精确筛选")] = None,
        ownerPhone: Annotated[str | None, Field(description="按主人电话精确筛选")] = None,
        species: Annotated[str | None, Field(description="按种类筛选，如：犬 / 猫")] = None,
        doctor: Annotated[str | None, Field(description="按主治医生精确筛选")] = None,
        disease: Annotated[str | None, Field(description="按疾病精确筛选")] = None,
        status: Annotated[
            str | None,
            Field(description="按就诊状态筛选，如：待就诊 / 就诊中 / 住院中 / 已康复 / 慢性病随访"),
        ] = None,
        min: Annotated[float | None, Field(description="按总花费下限（>=）筛选")] = None,
        max: Annotated[float | None, Field(description="按总花费上限（<=）筛选")] = None,
        sortBy: Annotated[str | None, Field(description="排序字段，如 totalCost / name / visitCount")] = None,
        order: Annotated[Literal["asc", "desc"] | None, Field(description="排序方向 asc|desc")] = None,
        page: Annotated[int, Field(ge=1, description="页码，从 1 开始，默认 1")] = 1,
        pageSize: Annotated[int, Field(ge=1, le=100, description="每页条数，默认 10，上限 100")] = 10,
    ) -> str:
        params = ListPets(
            q=q,
            name=name,
            ownerName=ownerName,
            ownerPhone=ownerPhone,
            species=species,
            doctor=doctor,
            disease=disease,
            status=status,
            min=min,
            max=max,
            sortBy=sortBy,
            order=order,
            page=page,
            pageSize=pageSize,
        )
        try:
            data = await api.list_pets(_build_query(params))
        except UpstreamError as exc:
            return CallToolResult(content=[TextContent(type="text", text=str(exc))], is_error=True)
        return render_result(data, page_size=params.pageSize)

    return handler


def register(server: MCPServer, api: PetApi) -> None:
    """向 server 注册 list_pets 工具（固定名称；SSE 说明写了分页规则）。"""
    server.add_tool(
        make_handler(api),
        name="list_pets",
        title="列出宠物档案",
        description=(
            "列出宠物档案清单，支持跨字段全文检索、精确筛选（姓名/主人/电话/种类/医生/疾病/状态）、"
            "总花费区间、排序与分页。不传任何筛选参数 = 返回首页前 10 条。返回中文摘要与数据 JSON 摘要。"
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        structured_output=False,
    )

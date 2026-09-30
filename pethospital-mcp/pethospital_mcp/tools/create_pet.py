"""create_pet 工具：CreatePet 参数模型 + 处理器 + 结果渲染。

新增宠物 = 一次上游 POST /api/v1/pets（无状态，不携带跨调用状态）。
必填字段与上游校验一致：name / ownerName / ownerPhone / doctor / disease。
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from ..petapi import PetApi, UpstreamError


class CreatePet(BaseModel):
    """create_pet 的参数模型：必填四项 + 可选档案字段。"""

    name: str = Field(description="宠物姓名（必填）")
    ownerName: str = Field(description="主人姓名（必填）")
    ownerPhone: str = Field(description="主人电话（必填）")
    doctor: str = Field(description="主治医生（必填）")
    disease: str = Field(description="疾病名称（必填）")
    species: str | None = Field(default=None, description="种类，如：犬 / 猫")
    breed: str | None = Field(default=None, description="品种，如：金毛")
    gender: str | None = Field(default=None, description="性别：公 / 母")
    ageMonths: int | None = Field(default=None, ge=0, description="年龄（月龄），>=0")
    color: str | None = Field(default=None, description="毛色")
    ownerAddr: str | None = Field(default=None, description="主人住址")
    status: str | None = Field(
        default=None,
        description="就诊状态：待就诊 / 就诊中 / 住院中 / 已康复 / 慢性病随访（不填上游默认待就诊）",
    )
    allergy: str | None = Field(default=None, description="过敏史，如：无 / 磺胺类药物过敏")
    chipNo: str | None = Field(default=None, description="芯片号码")

    def payload(self) -> dict[str, Any]:
        """去掉空值，只把用户显式给出的字段上送给上游。"""
        return {key: value for key, value in self.model_dump().items() if value is not None}


def _fmt_created(item: dict[str, Any]) -> str:
    """把新建的宠物渲染成一行中文摘要。"""
    parts = [item.get("id", ""), item.get("name", "")]
    if item.get("species"):
        parts.append(f"({item['species']})")
    for label, key in (
        ("主人", "ownerName"),
        ("电话", "ownerPhone"),
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


def render_result(created: dict[str, Any]) -> str:
    """渲染中文可读摘要 + 完整数据 JSON（新建档案通常很短，无需截断）。"""
    lines = [f"新增成功，宠物号 {created.get('id', '')}。", ""]
    lines.append("宠物档案：")
    lines.append(_fmt_created(created))
    lines.extend(["", "数据 JSON 摘要："])
    lines.append(json.dumps(created, ensure_ascii=False, indent=2))
    return "\n".join(lines)


def make_handler(api: PetApi):
    """创建 create_pet 处理器：参数为扁平签名，SDK 据此生成 inputSchema 并校验。"""

    async def handler(
        name: Annotated[str, Field(description="宠物姓名（必填）")],
        ownerName: Annotated[str, Field(description="主人姓名（必填）")],
        ownerPhone: Annotated[str, Field(description="主人电话（必填）")],
        doctor: Annotated[str, Field(description="主治医生（必填）")],
        disease: Annotated[str, Field(description="疾病名称（必填）")],
        species: Annotated[str | None, Field(description="种类，如：犬 / 猫")] = None,
        breed: Annotated[str | None, Field(description="品种，如：金毛")] = None,
        gender: Annotated[str | None, Field(description="性别：公 / 母")] = None,
        ageMonths: Annotated[int | None, Field(ge=0, description="年龄（月龄），>=0")] = None,
        color: Annotated[str | None, Field(description="毛色")] = None,
        ownerAddr: Annotated[str | None, Field(description="主人住址")] = None,
        status: Annotated[
            str | None,
            Field(description="就诊状态：待就诊 / 就诊中 / 住院中 / 已康复 / 慢性病随访（不填上游默认待就诊）"),
        ] = None,
        allergy: Annotated[str | None, Field(description="过敏史，如：无 / 磺胺类药物过敏")] = None,
        chipNo: Annotated[str | None, Field(description="芯片号码")] = None,
    ) -> str:
        params = CreatePet(
            name=name,
            ownerName=ownerName,
            ownerPhone=ownerPhone,
            doctor=doctor,
            disease=disease,
            species=species,
            breed=breed,
            gender=gender,
            ageMonths=ageMonths,
            color=color,
            ownerAddr=ownerAddr,
            status=status,
            allergy=allergy,
            chipNo=chipNo,
        )
        try:
            created = await api.create_pet(params.payload())
        except UpstreamError as exc:
            return CallToolResult(content=[TextContent(type="text", text=str(exc))], is_error=True)
        return render_result(created)

    return handler


def register(server: MCPServer, api: PetApi) -> None:
    """向 server 注册 create_pet 工具（写操作，不做只读/幂等标记）。"""
    server.add_tool(
        make_handler(api),
        name="create_pet",
        title="新增宠物档案",
        description=(
            "新增一只宠物档案。必填：name、ownerName、ownerPhone、doctor、disease；"
            "其余（species/breed/gender/ageMonths/color/ownerAddr/status/allergy/chipNo）可选。"
            "成功会上游自动分配 ID（如 PET-000001）并返回完整档案；参数缺失或非法时返回可操作错误。"
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
        structured_output=False,
    )

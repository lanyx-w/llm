"""test_list_pets.py：end-to-end，Client 连内存 server 调 list_pets。"""

from __future__ import annotations

import asyncio

from conftest import make_data, make_pet
from mcp import Client

from pethospital_mcp.server import build_server


def _run(coro):
    return asyncio.run(coro)


def _ten_pets() -> list[dict]:
    return [make_pet(pid=f"PET-{i:06d}", name=f"宠物{i:02d}", total_cost=1000.0 + i) for i in range(10)]


async def _call(server, arguments: dict):
    async with Client(server) as client:
        return await client.call_tool("list_pets", arguments)


async def _call_create(server, arguments: dict):
    async with Client(server) as client:
        return await client.call_tool("create_pet", arguments)


def test_no_args_returns_first_page_10(stub_upstream):
    stub_upstream.state.payload["data"] = make_data(_ten_pets(), total=105, page=1)
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(_call(server, {}))

    assert result.is_error is False
    text = result.content[0].text
    assert "共命中 105 条" in text
    assert "第 1 页" in text
    assert "本页 10 条" in text
    for pid in ("PET-000000", "PET-000009"):
        assert pid in text
    assert "总花费" in text
    assert "就诊" in text
    assert "数据 JSON 摘要" in text
    # 发往桩上游的 query：无参数时也应显式带上默认分页
    query = stub_upstream.query_of()
    assert query["page"] == "1"
    assert query["pageSize"] == "10"
    # 超长结果截断提示
    assert "已有 105 条命中，建议缩小筛选或翻页查看" in text


def test_filter_and_cost_range_params(stub_upstream):
    stub_upstream.state.payload["data"] = make_data(_ten_pets(), total=391)
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(
        _call(
            server,
            {"species": "犬", "min": 1000.5, "max": 2000, "sortBy": "totalCost", "order": "desc", "pageSize": 5},
        )
    )

    assert result.is_error is False
    query = stub_upstream.query_of()
    assert query["species"] == "犬"
    assert query["min"] == "1000.5"
    assert query["max"] == "2000"
    assert query["sortBy"] == "totalCost"
    assert query["order"] == "desc"
    assert query["pageSize"] == "5"
    assert '"pageSize": 5' in result.content[0].text


def test_q_fulltext_and_pagination(stub_upstream):
    stub_upstream.state.payload["data"] = make_data(_ten_pets(), total=38, page=3, page_size=7)
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(_call(server, {"q": "肠胃炎", "page": 3, "pageSize": 7}))

    assert result.is_error is False
    query = stub_upstream.query_of()
    assert query["q"] == "肠胃炎"
    assert query["page"] == "3"
    assert query["pageSize"] == "7"
    text = result.content[0].text
    assert "第 3 页" in text
    assert "共命中 38 条" in text


def test_exact_filters_each_passthrough(stub_upstream):
    stub_upstream.state.payload["data"] = make_data(_ten_pets(), total=1)
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(
        _call(
            server,
            {
                "name": "旺财",
                "ownerName": "张三",
                "ownerPhone": "13800001111",
                "doctor": "李医生",
                "disease": "急性肠胃炎",
                "status": "待就诊",
            },
        )
    )

    assert result.is_error is False
    query = stub_upstream.query_of()
    for key in ("name", "ownerName", "ownerPhone", "doctor", "disease", "status"):
        assert key in query


def test_sort_order_params(stub_upstream):
    stub_upstream.state.payload["data"] = make_data(_ten_pets(), total=1008)
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(_call(server, {"sortBy": "name", "order": "asc"}))

    assert result.is_error is False
    query = stub_upstream.query_of()
    assert query["sortBy"] == "name"
    assert query["order"] == "asc"
    # JSON 摘要包含 total/pageSize/totalPages
    text = result.content[0].text
    assert '"pageSize": 10' in text
    assert '"totalPages": 101' in text


def test_upstream_500_returns_is_error(stub_upstream):
    stub_upstream.state.status = 500
    stub_upstream.state.payload = {"code": 500, "message": "boom"}
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(_call(server, {}))

    assert result.is_error is True
    assert "HTTP 500" in result.content[0].text


def test_disconnected_upstream_returns_is_error():
    server = build_server(upstream="http://127.0.0.1:1", timeout=0.5)

    result = _run(_call(server, {}))

    assert result.is_error is True
    assert "无法连接上游" in result.content[0].text


def test_invalid_arguments_rejected(stub_upstream):
    stub_upstream.state.payload["data"] = make_data([], total=0)
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(_call(server, {"pageSize": 500}))

    assert result.is_error is True
    # 等价于结构化参数错误：SDK 以 is_error 结果返回
    assert "list_pets" in result.content[0].text
    assert "pageSize" in result.content[0].text


def test_create_pet_end_to_end(stub_upstream):
    stub_upstream.state.payload = {
        "code": 201,
        "message": "新增成功，宠物号 PET-909001",
        "data": make_pet(pid="PET-909001", name="豆豆", species="猫", doctor="王医生", disease="皮肤病"),
        "time": "",
    }
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(
        _call_create(
            server,
            {
                "name": "豆豆",
                "species": "猫",
                "ownerName": "李四",
                "ownerPhone": "13800002222",
                "doctor": "王医生",
                "disease": "皮肤病",
                "status": "待就诊",
            },
        )
    )

    assert result.is_error is False
    text = result.content[0].text
    assert "新增成功" in text
    assert "PET-909001" in text
    assert "豆豆" in text
    assert "数据 JSON 摘要" in text
    # 发往桩上游的是 POST /api/v1/pets，且只含用户显式字段
    path, body = stub_upstream.state.posts[-1]
    assert path == "/api/v1/pets"
    assert body["name"] == "豆豆"
    assert body["species"] == "猫"
    assert body["status"] == "待就诊"
    assert "ageMonths" not in body


def test_create_pet_missing_required_schema_rejected(stub_upstream):
    stub_upstream.state.payload = {"code": 201, "message": "ok", "data": make_pet(), "time": ""}
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    result = _run(_call_create(server, {"name": "豆豆", "ownerName": "李四"}))

    assert result.is_error is True
    assert "create_pet" in result.content[0].text
    assert "ownerPhone" in result.content[0].text


def test_create_pet_schema_has_required_fields(stub_upstream):
    stub_upstream.state.payload = {"code": 201, "message": "ok", "data": make_pet(), "time": ""}
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    async def inner():
        async with Client(server) as client:
            res = await client.list_tools()
            return res

    res = _run(inner())
    create = next(tool for tool in res.tools if tool.name == "create_pet")
    props = create.input_schema.get("properties", {})
    for key in ("name", "ownerName", "ownerPhone", "doctor", "disease"):
        assert key in props
        assert props[key].get("type") == "string"
    required = create.input_schema.get("required", [])
    assert set(required) == {"name", "ownerName", "ownerPhone", "doctor", "disease"}
    # 写操作：不标记只读/幂等
    assert create.annotations.read_only_hint is False
    assert create.annotations.idempotent_hint is False


def test_tool_registration_order_and_schema(stub_upstream):
    stub_upstream.state.payload["data"] = make_data([], total=0)
    server = build_server(upstream=stub_upstream.base_url, timeout=2.0)

    async def inner():
        async with Client(server) as client:
            res = await client.list_tools()
            return res

    res = _run(inner())
    names = [tool.name for tool in res.tools]
    assert names == ["list_pets", "create_pet"]
    schema = res.tools[0].input_schema
    props = schema.get("properties", {})
    keys = (
        "q",
        "name",
        "ownerName",
        "ownerPhone",
        "species",
        "doctor",
        "disease",
        "status",
        "min",
        "max",
        "sortBy",
        "order",
        "page",
        "pageSize",
    )
    for key in keys:
        assert key in props
    assert schema["properties"]["pageSize"].get("maximum") == 100
    assert schema["properties"]["pageSize"].get("minimum") == 1
    # 工具表静态，tools/list 结果带缓存 hint
    assert res.ttl_ms == 300_000
    assert res.cache_scope == "public"
    # 纯文本工具，不发布结构化输出 schema
    assert res.tools[0].output_schema is None

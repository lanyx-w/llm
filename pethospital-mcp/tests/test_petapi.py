"""test_petapi.py：桩上游验证信封解析、参数透传，与三种异常的错误映射。"""

from __future__ import annotations

import asyncio

import pytest
from conftest import make_data, make_pet

from pethospital_mcp.petapi import PetApi, UpstreamError


def _run(coro):
    return asyncio.run(coro)


def test_envelope_parse(stub_upstream):
    stub_upstream.state.payload["data"] = make_data(
        [make_pet(pid="PET-000001", total_cost=1000.0), make_pet(pid="PET-000002", total_cost=500.0)],
        total=2,
    )
    api = PetApi(stub_upstream.base_url)
    try:
        data = _run(api.list_pets({"page": 1, "pageSize": 10}))
    finally:
        _run(api.aclose())
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["pageSize"] == 10
    assert [item["id"] for item in data["items"]] == ["PET-000001", "PET-000002"]


def test_query_params_forwarded(stub_upstream):
    stub_upstream.state.payload["data"] = make_data([], total=0)
    api = PetApi(stub_upstream.base_url)
    try:
        _run(api.list_pets({"species": "犬", "min": 1000, "max": 2000, "sortBy": "totalCost", "order": "desc"}))
    finally:
        _run(api.aclose())
    query = stub_upstream.query_of()
    assert query["species"] == "犬"
    assert query["min"] == "1000"
    assert query["max"] == "2000"
    assert query["sortBy"] == "totalCost"
    assert query["order"] == "desc"


def test_connection_failure_is_actionable():
    api = PetApi("http://127.0.0.1:1", timeout=0.5)
    try:
        with pytest.raises(UpstreamError) as exc:
            _run(api.list_pets({}))
        assert "无法连接上游" in str(exc.value)
        assert "http://127.0.0.1:1" in str(exc.value)
    finally:
        _run(api.aclose())


def test_http_500_maps_status_and_body(stub_upstream):
    stub_upstream.state.status = 500
    stub_upstream.state.payload = {"code": 500, "message": "internal boom"}
    api = PetApi(stub_upstream.base_url)
    try:
        with pytest.raises(UpstreamError) as exc:
            _run(api.list_pets({}))
    finally:
        _run(api.aclose())
    assert "HTTP 500" in str(exc.value)
    assert "internal boom" in str(exc.value)


def test_code_not_200_carries_upstream_message(stub_upstream):
    stub_upstream.state.status = 200
    stub_upstream.state.payload = {"code": 400, "message": "参数错误", "data": None, "time": ""}
    api = PetApi(stub_upstream.base_url)
    try:
        with pytest.raises(UpstreamError) as exc:
            _run(api.list_pets({}))
    finally:
        _run(api.aclose())
    assert "参数错误" in str(exc.value)


def test_create_pet_posts_payload_and_parses_201(stub_upstream):
    stub_upstream.state.payload = {
        "code": 201,
        "message": "新增成功，宠物号 PET-000001",
        "data": make_pet(pid="PET-000001", name="豆豆", species="猫"),
        "time": "",
    }
    api = PetApi(stub_upstream.base_url)
    try:
        created = _run(
            api.create_pet(
                {"name": "豆豆", "species": "猫", "ownerName": "李四", "ownerPhone": "13800002222",
                 "doctor": "王医生", "disease": "皮肤病"}
            )
        )
    finally:
        _run(api.aclose())
    assert created["id"] == "PET-000001"
    assert created["name"] == "豆豆"
    path, body = stub_upstream.state.posts[-1]
    assert path == "/api/v1/pets"
    assert body["name"] == "豆豆"
    assert body["species"] == "猫"
    # 用户没给的字段（ageMonths 等）不上送
    assert "ageMonths" not in body
    assert "breed" not in body


def test_create_pet_business_error_maps_message(stub_upstream):
    stub_upstream.state.status = 200
    stub_upstream.state.payload = {"code": 400, "message": "ownerPhone 不能为空", "data": None, "time": ""}
    api = PetApi(stub_upstream.base_url)
    try:
        with pytest.raises(UpstreamError) as exc:
            _run(api.create_pet({"name": "豆豆"}))
    finally:
        _run(api.aclose())
    assert "ownerPhone 不能为空" in str(exc.value)


def test_create_pet_http_500_maps_status(stub_upstream):
    stub_upstream.state.status = 500
    stub_upstream.state.payload = {"code": 500, "message": "boom"}
    api = PetApi(stub_upstream.base_url)
    try:
        with pytest.raises(UpstreamError) as exc:
            _run(api.create_pet({"name": "豆豆"}))
    finally:
        _run(api.aclose())
    assert "HTTP 500" in str(exc.value)


def test_create_pet_connection_failure_is_actionable():
    api = PetApi("http://127.0.0.1:1", timeout=0.5)
    try:
        with pytest.raises(UpstreamError) as exc:
            _run(api.create_pet({"name": "豆豆"}))
        assert "无法连接上游" in str(exc.value)
    finally:
        _run(api.aclose())

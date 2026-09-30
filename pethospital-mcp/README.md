# pethospital-mcp

宠物医院 REST API 的 MCP Server（工具：`list_pets` / `create_pet`）。把本机运行中的宠物医院服务（127.0.0.1:8080）封装为 MCP 工具，同时支持 **stdio** 与 **Streamable HTTP** 两种传输，是无状态桥梁：一次 `list_pets` = 一次上游 GET、一次 `create_pet` = 一次上游 POST，不携带跨调用状态。

## 安装

需要 Python >= 3.11。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

开发依赖（pytest / ruff）在 `dev` extra 中；运行时只需要 `mcp>=2.0.0` 与 `httpx`。

## 配置项

| 命令行参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-upstream` | `http://127.0.0.1:8080` | 上游宠物医院 API 地址；环境变量 `PETHOSPITAL_UPSTREAM` 可覆盖 |
| `-addr` | 空 | HTTP 监听地址，如 `127.0.0.1:18080`；给出则额外运行 Streamable HTTP（挂载 `/mcp`，另有 `GET /health` 健康检查） |
| `-stdio` | true | 启用 stdio 传输；与 `-addr` 同时给出时并发运行 |
| `-no-stdio` | - | 关闭 stdio（HTTP 独立运行，避免 stdout 被协议之外内容污染） |
| `-timeout` | 15 | 上游请求超时（秒） |

启动前请确认宠物医院服务已在 `-upstream` 指定的地址运行。

## 工具说明

### list_pets

`/api/pet/list` 的 MCP 封装，支持以下筛选/排序/分页参数（均为可选）：

- `q`：全文检索（宠物名/主人/疾病/病历等）
- `name` / `ownerName` / `ownerPhone` / `doctor` / `disease` / `status`：精确筛选
- `species`：物种（如 `犬`）
- `min` / `max`：总花费区间
- `sortBy`：排序字段（如 `totalCost`、`name`），配合 `order`（`asc`/`desc`）
- `page` / `pageSize`：分页，默认第 1 页每页 10 条（`pageSize` 上限 100）

返回人类可读的候选列表、分页摘要与 JSON 摘要；结果过长时截断并提示缩小筛选或翻页。

### create_pet

`POST /api/v1/pets` 的 MCP 封装，新增一只宠物档案。必填参数（与上游校验一致）：

- `name` / `ownerName` / `ownerPhone` / `doctor` / `disease`

可选参数：`species`（如 `犬`）、`breed`、`gender`（`公`/`母`）、`ageMonths`、`color`、
`ownerAddr`、`status`（不填上游默认 `待就诊`）、`allergy`、`chipNo`。

成功返回上游自动分配的宠物号（如 `PET-000001`）与完整档案 JSON；参数缺失或非法、上游
返回业务错误时返回 `is_error=true` 且附带可操作提示。

## MCP 客户端接入

### stdio 版

```json
{
  "mcpServers": {
    "pethospital": {
      "command": "D:\\AI\\pet-hospital-windows-amd64\\windows\\pethospital-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "pethospital_mcp",
        "-stdio",
        "-upstream",
        "http://127.0.0.1:8080"
      ]
    }
  }
}
```

可用 `pethospital-mcp`（pyproject 注册的命令）代替完整 python 路径，前提是 venv 已在 PATH 中。

### HTTP 版

```json
{
  "mcpServers": {
    "pethospital": {
      "url": "http://127.0.0.1:18080/mcp",
      "type": "http"
    }
  }
}
```

本地先启动 HTTP 传输：

```powershell
.\.venv\Scripts\python.exe -m pethospital_mcp -addr 127.0.0.1:18080 -no-stdio
```

健康检查：`GET http://127.0.0.1:18080/health`。

## 测试

```powershell
python -m pytest
ruff check .
python -m pethospital_mcp -h
```

`tests/` 使用线程内 `http.server` 桩上游（固定信封、可配置状态码/延迟/乱序），覆盖信封解析、参数透传、连接失败/HTTP 5xx/`code!=200` 错误映射，以及 `Client(server)` 内存端到端调用。

## 常见问题

- **提示"无法连接上游，请确认 pethospital 是否在 http://127.0.0.1:8080 运行"**：上游进程没启动或端口不对。启动 `pethospital.exe`（联网校验可加 `--develop https://**` 跳过），或用 `-upstream` 指到实际地址。
- **工具列表为空 / 无 `list_pets`**：确认安装版本满足 `mcp>=2.0.0`（本 SDK v2 协议 2026-07-28），旧版 `@mcp.server.fastmcp` 写法不兼容。
- **HTTP 版连不上**：确认服务加了 `-addr` 且 `-no-stdio`（或忽略 stdio），并 ping 通 `GET /health`（返回 HTTP 200 即存活）。
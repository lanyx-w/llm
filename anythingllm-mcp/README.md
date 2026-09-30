# anythingllm-mcp

MCP server（2026-07-28 协议）通过 stdio 暴露一个工具 `ask_workspace`，基于本地 AnythingLLM 单一工作区做问答，只使用工作区内容，无相关内容时明确说明而不编造。

## 安装

```
pip install -e ".[dev]"
```

## 配置

复制 `.env.example` 为 `.env` 并填写：

- `ANYTHINGLLM_BASE_URL`：AnythingLLM 地址，默认 `http://localhost:3001`
- `ANYTHINGLLM_API_KEY`：必填，缺失时启动即失败
- `ANYTHINGLLM_WORKSPACE_SLUG`：可选；留空时自动采用唯一工作区（多个时需指定 slug）

## 运行

serve 模式（供 MCP 客户端连接）：

```
anythingllm-mcp
```

开发调试（MCP Inspector）：

```
mcp dev server.py
```

未安装 CLI 时可用：`uv run --with "mcp[cli]" mcp dev server.py`

## 测试

```
pytest
```

集成用例依赖本机 AnythingLLM 与 `ANYTHINGLLM_API_KEY`，服务未启动时自动跳过。
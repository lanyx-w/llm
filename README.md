# llm

基于 AnythingLLM 与 MCP（Model Context Protocol）的本地 LLM 应用集合，包含两个 MCP 服务器与一个 AnythingLLM 管理台，以及 opencode 的 MCP 接入配置。

## 项目结构

| 目录 | 说明 |
| --- | --- |
| [`anythingllm-mcp`](anythingllm-mcp) | 封装本地 AnythingLLM 单一工作区的 MCP 服务器（工具：`ask_workspace`），仅基于工作区内容作答 |
| [`AnythingLLMServer`](AnythingLLMServer) | 纯前端 AnythingLLM 管理台（单文件 `index.html`），管理工作区、上传文档、浏览文档树 |
| [`pethospital-mcp`](pethospital-mcp) | 宠物医院 REST API 的 MCP 服务器（工具：`list_pets` / `create_pet`），支持 stdio 与 Streamable HTTP |

## anythingllm-mcp

MCP 服务器（2026-07-28 协议），通过 stdio 暴露 `ask_workspace` 工具，基于本地 AnythingLLM 单一工作区做问答，只使用工作区内容，无相关内容时明确说明而不编造。

```powershell
pip install -e ".[dev]"
anythingllm-mcp
```

详见 [`anythingllm-mcp/README.md`](anythingllm-mcp/README.md)。

## AnythingLLMServer

单文件前端管理台，浏览器直接打开 `index.html` 即可使用（默认对接 `http://localhost:3001/api/v1`）：

- 工作区增删与切换
- 文档上传与嵌入（含 token 统计）
- 文档树浏览与删除

## pethospital-mcp

宠物医院 REST API 的 MCP 服务器，把本机运行中的宠物医院服务（`127.0.0.1:8080`）封装为 MCP 工具，支持 **stdio** 与 **Streamable HTTP** 两种传输。

```powershell
pip install -e ".[dev]"
python -m pethospital_mcp -stdio
```

详见 [`pethospital-mcp/README.md`](pethospital-mcp/README.md)。

## opencode 配置

opencode 的 MCP 接入配置位于仓库外的 `D:/AI/opencode.json`（保留在 AI 根目录，供本地 opencode 使用），其中配置了两个 MCP：

- `modelscope`：远程 MCP
- `anythingllm`：本地 MCP（指向 `anythingllm-mcp`，环境变量文件为 `D:/AI/LLM/anythingllm-mcp/.env`）

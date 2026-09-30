import os
import sys

from mcp.server import MCPServer

from .client import AnythingLLMClient, AnythingLLMError
from .env import load_dotenv


def load_config() -> tuple[AnythingLLMClient, str]:
    load_dotenv(os.getenv("ANYTHINGLLM_ENV_FILE"))
    base_url = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001")
    api_key = os.getenv("ANYTHINGLLM_API_KEY", "").strip()
    if not api_key:
        sys.exit("错误: 缺少 ANYTHINGLLM_API_KEY 环境变量（可在 .env 中配置）")
    client = AnythingLLMClient(base_url, api_key)
    try:
        workspaces = client.list_workspaces()
    except AnythingLLMError as e:
        sys.exit(f"错误: {e}")
    slug = os.getenv("ANYTHINGLLM_WORKSPACE_SLUG", "").strip()
    if not slug:
        if len(workspaces) != 1:
            names = "、".join(w.get("name", w.get("slug", "?")) for w in workspaces) or "（无工作区）"
            sys.exit(f"错误: 期望恰好一个工作区，当前 {len(workspaces)} 个: {names}；请设置 ANYTHINGLLM_WORKSPACE_SLUG")
        slug = workspaces[0]["slug"]
    elif not any(w.get("slug") == slug for w in workspaces):
        available = ", ".join(w.get("slug", "?") for w in workspaces) or "（无工作区）"
        sys.exit(f"错误: 工作区 {slug} 不存在，可用的: {available}")
    return client, slug


def render(chat_response: dict) -> str:
    if chat_response.get("error"):
        raise AnythingLLMError(f"AnythingLLM 返回错误: {chat_response['error']}")
    text = (chat_response.get("textResponse") or "").strip()
    if not text:
        return "工作区中没有可以回答该问题的相关内容"
    sources = chat_response.get("sources") or []
    lines = [text, "", "来源:"]
    if not sources:
        lines.append("（无引用来源）")
    for s in sources:
        chunk = (s.get("chunk") or "").strip()
        lines.append(f"- {s.get('title') or '?'}: {chunk[:120]}")
    return "\n".join(lines)


def make_server(client: AnythingLLMClient, slug: str) -> MCPServer:
    mcp = MCPServer("anythingllm")

    @mcp.tool()
    def ask_workspace(question: str) -> str:
        """仅基于工作区知识库回答用户的问题；无相关内容时明确说明，不编造。"""
        return render(client.chat(slug, question))

    return mcp


def main() -> None:
    client, slug = load_config()
    make_server(client, slug).run()


if __name__ == "__main__":
    main()
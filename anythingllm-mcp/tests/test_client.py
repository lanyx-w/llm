import os
import socket

import pytest

from anythingllm_mcp.client import AnythingLLMClient
from anythingllm_mcp.env import load_dotenv

load_dotenv()
BASE_URL = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001")
API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "").strip()


def _server_up() -> bool:
    try:
        with socket.create_connection(("localhost", 3001), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not (_server_up() and API_KEY), reason="需要本地 AnythingLLM 及 ANYTHINGLLM_API_KEY"
)


def test_workspaces_and_chat():
    client = AnythingLLMClient(BASE_URL, API_KEY)
    workspaces = client.list_workspaces()
    assert workspaces
    resp = client.chat(workspaces[0]["slug"], "你好")
    assert "textResponse" in resp
    assert "error" in resp
import pytest

from anythingllm_mcp import server as server_module
from anythingllm_mcp.client import AnythingLLMError
from anythingllm_mcp.server import render


def test_render_full():
    out = render({"textResponse": "答案", "sources": [{"title": "a.txt", "chunk": "context"}]})
    assert "答案" in out
    assert "a.txt" in out
    assert "context" in out


def test_render_no_hits():
    out = render({"textResponse": "", "sources": []})
    assert "没有可以回答该问题" in out


def test_render_error():
    with pytest.raises(AnythingLLMError):
        render({"error": "boom"})


def test_missing_api_key(monkeypatch):
    monkeypatch.setattr(server_module, "load_dotenv", lambda _: None)
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        server_module.load_config()


def test_workspace_too_many(monkeypatch):
    monkeypatch.setattr(server_module, "load_dotenv", lambda _: None)
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "k")
    monkeypatch.delenv("ANYTHINGLLM_WORKSPACE_SLUG", raising=False)

    class FakeClient:
        def list_workspaces(self):
            return [{"slug": "a"}, {"slug": "b"}]

    monkeypatch.setattr(server_module, "AnythingLLMClient", lambda *a, **k: FakeClient())
    with pytest.raises(SystemExit) as e:
        server_module.load_config()
    assert "2 个" in str(e.value)


def test_single_workspace_autodetect(monkeypatch):
    monkeypatch.setattr(server_module, "load_dotenv", lambda _: None)
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "k")
    monkeypatch.delenv("ANYTHINGLLM_WORKSPACE_SLUG", raising=False)

    class FakeClient:
        def list_workspaces(self):
            return [{"slug": "solo"}]

    monkeypatch.setattr(server_module, "AnythingLLMClient", lambda *a, **k: FakeClient())
    _, slug = server_module.load_config()
    assert slug == "solo"
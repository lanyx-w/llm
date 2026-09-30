import json
import urllib.error
import urllib.request


class AnythingLLMError(RuntimeError):
    pass


class AnythingLLMClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                pass
            raise AnythingLLMError(f"HTTP {e.code}: {detail or e.reason}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise AnythingLLMError(
                f"无法连接 AnythingLLM ({self.base_url + path}): {e}"
            ) from e

    def list_workspaces(self) -> list[dict]:
        return self._request("GET", "/api/v1/workspaces").get("workspaces", [])

    def chat(self, slug: str, message: str) -> dict:
        return self._request(
            "POST",
            f"/api/v1/workspace/{slug}/chat",
            {"message": message, "mode": "query"},
        )
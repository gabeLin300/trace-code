from trace_code.config import TraceSettings
from trace_code.tools import executor


class _FakeWebSearchClient:
    def __init__(self, command):
        self.command = command

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def search(self, query, max_results=5, search_depth="basic"):
        return {
            "status": "ok",
            "answer": "Mocked web answer",
            "results": [
                {
                    "title": "Result 1",
                    "url": "https://example.com/r1",
                    "content": "This is a mocked web search snippet.",
                    "score": 0.9,
                }
            ],
        }


class _FailingWebSearchClient:
    def __init__(self, command):
        pass

    def __enter__(self):
        raise executor.WebSearchMCPClientError("server unavailable")

    def __exit__(self, exc_type, exc, tb):
        return None


def test_prompt_requests_tool_for_web_search() -> None:
    assert executor.prompt_requests_tool("search web for langchain memory")
    assert executor.prompt_requests_tool("web search for Tavily")


def test_execute_web_search_via_mcp(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(executor, "WebSearchMCPClient", _FakeWebSearchClient)

    result = executor.execute_tool_from_prompt(
        "search web for latest langchain docs",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "web.search"
    assert "Mocked web answer" in result["output"]
    assert "https://example.com/r1" in result["output"]


def test_execute_web_search_falls_back_to_direct_tavily(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(executor, "WebSearchMCPClient", _FailingWebSearchClient)
    monkeypatch.setattr(executor, "resolve_tavily_api_key", lambda **kwargs: "api-key")
    monkeypatch.setattr(
        executor,
        "tavily_search",
        lambda **kwargs: {
            "status": "ok",
            "answer": "Fallback answer",
            "results": [
                {
                    "title": "Fallback Result",
                    "url": "https://example.com/fallback",
                    "content": "Fallback snippet",
                }
            ],
        },
    )

    result = executor.execute_tool_from_prompt(
        "web search for tavily mcp",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "web.search"
    assert "Fallback answer" in result["output"]
    assert "https://example.com/fallback" in result["output"]

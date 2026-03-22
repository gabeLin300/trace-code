import pytest

from trace_code.mcp import web_search_server as ws


def test_resolve_tavily_api_key_prefers_explicit(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "env-key")
    value = ws.resolve_tavily_api_key(explicit_api_key="arg-key", prompt_if_missing=False)
    assert value == "arg-key"


def test_resolve_tavily_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "env-key")
    value = ws.resolve_tavily_api_key(explicit_api_key=None, prompt_if_missing=False)
    assert value == "env-key"


def test_resolve_tavily_api_key_from_prompt(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(ws.getpass, "getpass", lambda prompt: "prompt-key")
    value = ws.resolve_tavily_api_key(explicit_api_key=None, prompt_if_missing=True)
    assert value == "prompt-key"


def test_resolve_tavily_api_key_raises_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(ws.TavilyError, match="Missing Tavily API key"):
        ws.resolve_tavily_api_key(explicit_api_key=None, prompt_if_missing=False)


def test_tavily_search_normalizes_results(monkeypatch) -> None:
    monkeypatch.setattr(
        ws,
        "_tavily_search_request",
        lambda **kwargs: {
            "answer": "Use RetrievalQA.",
            "results": [
                {
                    "title": "LangChain Retrieval",
                    "url": "https://python.langchain.com/docs/",
                    "content": "Retrieval guide",
                    "score": 0.9,
                }
            ],
        },
    )

    out = ws.tavily_search(api_key="k", query="langchain retrieval", max_results=3, search_depth="advanced")

    assert out["status"] == "ok"
    assert out["answer"] == "Use RetrievalQA."
    assert out["results"][0]["url"].startswith("https://")


def test_tavily_search_requires_query() -> None:
    with pytest.raises(ws.TavilyError, match="query must not be empty"):
        ws.tavily_search(api_key="k", query="   ")

import pytest

from trace_code.agent.loop import run_turn
from trace_code.llm.base import LLMResponse
from trace_code.llm.manager import LLMManager
from trace_code.mcp.router import route_tool
from trace_code.tools import executor


def test_agent_loop_branches(monkeypatch) -> None:
    monkeypatch.setattr(
        LLMManager,
        "generate",
        lambda self, prompt, provider_override=None: LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content=f"ok:{prompt}",
        ),
    )
    tool_path = run_turn("list files", wants_tool=True)
    answer_path = run_turn("explain code", wants_tool=False)

    assert tool_path["status"] == "tool_called"
    assert answer_path["status"] == "answered"


def test_mcp_router_namespaces() -> None:
    assert route_tool("fs.read") == "filesystem"
    assert route_tool("knowledge.search") == "local_knowledge"
    assert route_tool("web.search") == "web_search"


def test_mcp_router_rejects_unknown_namespace() -> None:
    with pytest.raises(ValueError):
        route_tool("unknown.action")


def test_agent_loop_knowledge_search_tool_path(monkeypatch) -> None:
    monkeypatch.setattr(
        executor,
        "search_langchain_docs",
        lambda **kwargs: {
            "results": [
                {
                    "text": "LangChain retrieval overview.",
                    "metadata": {"source_url": "https://python.langchain.com/docs/introduction/"},
                    "distance": 0.2,
                }
            ]
        },
    )

    result = run_turn(
        "search langchain docs for retrieval",
        wants_tool=True,
    )

    assert result["status"] == "tool_called"
    assert result["tool"] == "knowledge.search_langchain_docs"


def test_agent_loop_web_search_tool_path(monkeypatch) -> None:
    monkeypatch.setattr(
        executor,
        "_web_search_via_mcp",
        lambda query, settings, mcp_manager=None: {
            "status": "ok",
            "answer": "Web answer",
            "results": [
                {
                    "title": "LangChain",
                    "url": "https://python.langchain.com/docs/",
                    "content": "Docs content",
                }
            ],
        },
    )

    result = run_turn(
        "search web for langchain retrievers",
        wants_tool=True,
    )

    assert result["status"] == "tool_called"
    assert result["tool"] == "web.search"


def test_agent_loop_returns_requires_confirmation_for_non_read_shell() -> None:
    result = run_turn(
        "run command touch demo.txt",
        wants_tool=True,
    )

    assert result["status"] == "requires_confirmation"
    assert result["tool_status"] == "requires_confirmation"
    assert result["tool"] == "shell.exec"

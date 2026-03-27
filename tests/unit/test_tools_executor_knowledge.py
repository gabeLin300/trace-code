from trace_code.config import TraceSettings
from trace_code.tools import executor
import pytest


def test_prompt_requests_tool_for_langchain_knowledge() -> None:
    assert executor.prompt_requests_tool("ingest langchain docs")
    assert executor.prompt_requests_tool("search langchain docs for vectorstore")


def test_ingest_langchain_docs_tool(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        executor,
        "index_langchain_docs",
        lambda **kwargs: {
            "seed_url": kwargs["seed_url"],
            "pages_indexed": 2,
            "chunks_indexed": 12,
            "collection": kwargs["collection_name"],
        },
    )

    result = executor.execute_tool_from_prompt(
        "ingest langchain docs max pages 10",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "knowledge.ingest_langchain_docs"
    assert "pages_indexed=2" in result["output"]
    assert "chunks_indexed=12" in result["output"]


def test_search_langchain_docs_tool(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        executor,
        "search_langchain_docs",
        lambda **kwargs: {
            "results": [
                {
                    "text": "Use RetrievalQA and vector stores.",
                    "metadata": {"source_url": "https://python.langchain.com/docs/tutorials/"},
                    "distance": 0.11,
                }
            ]
        },
    )

    result = executor.execute_tool_from_prompt(
        "search langchain docs for retrieval qa",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "knowledge.search_langchain_docs"
    assert "https://python.langchain.com/docs/tutorials/" in result["output"]
    assert "RetrievalQA" in result["output"]


def test_search_langchain_docs_tool_bypasses_mcp_manager(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        executor,
        "search_langchain_docs",
        lambda **kwargs: {
            "results": [
                {
                    "text": "Retriever memory differs from agent memory.",
                    "metadata": {"source_url": "https://python.langchain.com/docs/concepts/memory/"},
                    "distance": 0.07,
                }
            ]
        },
    )

    class _FailingManager:
        def search_langchain_docs(self, query, top_k, collection):
            raise AssertionError("MCP search path should not be used")

    result = executor.execute_tool_from_prompt(
        "search langchain docs for retriever and agent memory differences",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
        mcp_manager=_FailingManager(),
    )

    assert result["tool_name"] == "knowledge.search_langchain_docs"
    assert "agent memory" in result["output"]


def test_search_langchain_docs_requires_query(tmp_path) -> None:
    with pytest.raises(executor.ToolExecutionError, match="missing query"):
        executor.execute_tool_from_prompt(
            "search langchain docs",
            workspace_root=tmp_path,
            settings=TraceSettings(workspace_root=tmp_path),
        )

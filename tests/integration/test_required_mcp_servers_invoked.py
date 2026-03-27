from __future__ import annotations

from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.tools.executor import execute_tool_from_prompt


class _TrackingMCPManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_files(self, directory: Path) -> str:
        self.calls.append("filesystem")
        return "README.md"

    def read_file(self, file_path: Path) -> str:
        self.calls.append("filesystem")
        return "content"

    def search_langchain_docs(self, query: str, top_k: int, collection: str) -> dict:
        self.calls.append("local_knowledge")
        return {"results": [{"text": "retrieval docs", "metadata": {"source_url": "https://example.com"}}]}

    def web_search(self, query: str, max_results: int, search_depth: str) -> dict:
        self.calls.append("web_search")
        return {"answer": "latest release", "results": []}


def test_required_mcp_servers_are_invoked_in_one_flow(tmp_path: Path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    mcp = _TrackingMCPManager()

    execute_tool_from_prompt("list files", workspace_root=tmp_path, settings=settings, mcp_manager=mcp)
    execute_tool_from_prompt("search web for latest langchain release", workspace_root=tmp_path, settings=settings, mcp_manager=mcp)
    execute_tool_from_prompt("search langchain docs for retrieval", workspace_root=tmp_path, settings=settings, mcp_manager=mcp)

    assert "filesystem" in mcp.calls
    assert "web_search" in mcp.calls
    assert "local_knowledge" in mcp.calls

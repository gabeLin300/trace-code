from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_code.config import TraceSettings
from trace_code.mcp.filesystem_client import FilesystemMCPClient, MCPClientError
from trace_code.mcp.local_knowledge_client import LocalKnowledgeMCPClient, LocalKnowledgeMCPClientError
from trace_code.mcp.web_search_client import WebSearchMCPClient, WebSearchMCPClientError


class MCPManagerError(RuntimeError):
    pass


@dataclass
class MCPHealth:
    filesystem: bool
    local_knowledge: bool
    web_search: bool


class MCPManager:
    """Owns MCP client lifecycle for one CLI session with reconnect on transient failures."""

    def __init__(self, settings: TraceSettings, workspace_root: Path):
        self.settings = settings
        self.workspace_root = workspace_root
        self._filesystem_client: FilesystemMCPClient | None = None
        self._local_knowledge_client: LocalKnowledgeMCPClient | None = None
        self._web_search_client: WebSearchMCPClient | None = None

    def start(self) -> None:
        # Eager startup for managed local MCP flows. Failures are tolerated and retried lazily on first use.
        if self.settings.mcp.mode not in {"managed", "hybrid"}:
            return
        self._try_start_filesystem()
        self._try_start_local_knowledge()
        self._try_start_web_search()

    def close(self) -> None:
        for client in (self._filesystem_client, self._local_knowledge_client, self._web_search_client):
            if client is None:
                continue
            client.close()
        self._filesystem_client = None
        self._local_knowledge_client = None
        self._web_search_client = None

    def health(self) -> MCPHealth:
        return MCPHealth(
            filesystem=self._is_running(self._filesystem_client),
            local_knowledge=self._is_running(self._local_knowledge_client),
            web_search=self._is_running(self._web_search_client),
        )

    def list_files(self, directory: Path) -> str:
        client = self._ensure_filesystem_client()
        try:
            return client.list_directory(directory)
        except MCPClientError:
            client = self._restart_filesystem_client()
            return client.list_directory(directory)

    def read_file(self, file_path: Path) -> str:
        client = self._ensure_filesystem_client()
        try:
            return client.read_file(file_path)
        except MCPClientError:
            client = self._restart_filesystem_client()
            return client.read_file(file_path)

    def ingest_langchain_docs(self, seed_url: str, max_pages: int, collection: str) -> dict[str, Any]:
        client = self._ensure_local_knowledge_client()
        try:
            return client.ingest_langchain_docs(seed_url=seed_url, max_pages=max_pages, collection=collection)
        except LocalKnowledgeMCPClientError:
            client = self._restart_local_knowledge_client()
            return client.ingest_langchain_docs(seed_url=seed_url, max_pages=max_pages, collection=collection)

    def search_langchain_docs(self, query: str, top_k: int, collection: str) -> dict[str, Any]:
        client = self._ensure_local_knowledge_client()
        try:
            return client.search_langchain_docs(query=query, top_k=top_k, collection=collection)
        except LocalKnowledgeMCPClientError:
            client = self._restart_local_knowledge_client()
            return client.search_langchain_docs(query=query, top_k=top_k, collection=collection)

    def web_search(self, query: str, max_results: int, search_depth: str) -> dict[str, Any]:
        client = self._ensure_web_search_client()
        try:
            return client.search(query=query, max_results=max_results, search_depth=search_depth)
        except WebSearchMCPClientError:
            client = self._restart_web_search_client()
            return client.search(query=query, max_results=max_results, search_depth=search_depth)

    def _is_running(self, client: Any | None) -> bool:
        if client is None:
            return False
        process = getattr(client, "process", None)
        if process is None:
            return False
        return process.poll() is None

    def _ensure_filesystem_client(self) -> FilesystemMCPClient:
        if not self._is_running(self._filesystem_client):
            self._filesystem_client = FilesystemMCPClient(
                command=self.settings.mcp.filesystem_server_argv(),
                workspace_root=self.workspace_root,
            )
            self._filesystem_client.start()
        return self._filesystem_client

    def _restart_filesystem_client(self) -> FilesystemMCPClient:
        if self._filesystem_client is not None:
            self._filesystem_client.close()
        self._filesystem_client = None
        return self._ensure_filesystem_client()

    def _ensure_local_knowledge_client(self) -> LocalKnowledgeMCPClient:
        if not self._is_running(self._local_knowledge_client):
            command = [
                *self.settings.mcp.local_knowledge_server_argv(),
                "--workspace-root",
                str(self.workspace_root),
            ]
            self._local_knowledge_client = LocalKnowledgeMCPClient(command=command)
            self._local_knowledge_client.start()
        return self._local_knowledge_client

    def _restart_local_knowledge_client(self) -> LocalKnowledgeMCPClient:
        if self._local_knowledge_client is not None:
            self._local_knowledge_client.close()
        self._local_knowledge_client = None
        return self._ensure_local_knowledge_client()

    def _ensure_web_search_client(self) -> WebSearchMCPClient:
        if not self._is_running(self._web_search_client):
            self._web_search_client = WebSearchMCPClient(command=self.settings.mcp.web_search_server_argv())
            self._web_search_client.start()
        return self._web_search_client

    def _restart_web_search_client(self) -> WebSearchMCPClient:
        if self._web_search_client is not None:
            self._web_search_client.close()
        self._web_search_client = None
        return self._ensure_web_search_client()

    def _try_start_filesystem(self) -> None:
        try:
            self._ensure_filesystem_client()
        except Exception:
            self._filesystem_client = None

    def _try_start_local_knowledge(self) -> None:
        try:
            self._ensure_local_knowledge_client()
        except Exception:
            self._local_knowledge_client = None

    def _try_start_web_search(self) -> None:
        try:
            self._ensure_web_search_client()
        except Exception:
            self._web_search_client = None

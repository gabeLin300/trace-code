from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Any

from trace_code.config import TraceSettings
from trace_code.mcp.filesystem_client import FilesystemMCPClient, MCPClientError
from trace_code.mcp.local_knowledge_client import LocalKnowledgeMCPClient, LocalKnowledgeMCPClientError
from trace_code.mcp.web_search_client import WebSearchMCPClient, WebSearchMCPClientError
from trace_code.utils.timeout import call_with_timeout


class MCPManagerError(RuntimeError):
    pass


@dataclass
class MCPHealth:
    filesystem: bool
    local_knowledge: bool
    web_search: bool


@dataclass
class MCPServerDiagnostic:
    connected: bool
    tools: list[str]
    startup_error: str
    executable: bool
    executable_detail: str
    failure_category: str
    remediation: str
    launch_command: list[str]
    python_executable: str
    virtual_env: str


class MCPManager:
    """Owns MCP client lifecycle for one CLI session with reconnect on transient failures."""

    def __init__(self, settings: TraceSettings, workspace_root: Path):
        self.settings = settings
        self.workspace_root = workspace_root
        self._filesystem_client: FilesystemMCPClient | None = None
        self._local_knowledge_client: LocalKnowledgeMCPClient | None = None
        self._web_search_client: WebSearchMCPClient | None = None
        self._startup_errors: dict[str, str] = {"filesystem": "", "local_knowledge": "", "web_search": ""}
        self._launch_commands: dict[str, list[str]] = {"filesystem": [], "local_knowledge": [], "web_search": []}
        self._startup_timeout_s: float = float(self.settings.mcp.startup_timeout_s)
        self._tools_timeout_s: float = float(self.settings.mcp.tools_timeout_s)
        self._operation_timeout_s: float = float(self.settings.mcp.operation_timeout_s)
        self._closed: bool = False

    def start(self) -> None:
        # Eager startup for managed local MCP flows. Failures are tolerated and retried lazily on first use.
        self._closed = False
        if self.settings.mcp.mode not in {"managed", "hybrid"}:
            return
        self._try_start_filesystem()
        self._try_start_local_knowledge()
        self._try_start_web_search()

    def prime(self) -> dict[str, str]:
        """Best-effort first-request warmup with bounded timeouts."""
        self._closed = False
        started: dict[str, str] = {}
        self._try_start_filesystem()
        self._try_start_local_knowledge()
        self._try_start_web_search()
        started["filesystem"] = self._startup_errors.get("filesystem", "") or "ok"
        started["local_knowledge"] = self._startup_errors.get("local_knowledge", "") or "ok"
        started["web_search"] = self._startup_errors.get("web_search", "") or "ok"
        return started

    def close(self) -> None:
        self._closed = True
        for client in (self._filesystem_client, self._local_knowledge_client, self._web_search_client):
            if client is None:
                continue
            client.close()
        self._filesystem_client = None
        self._local_knowledge_client = None
        self._web_search_client = None

    def health(self) -> MCPHealth:
        if self._closed:
            return MCPHealth(filesystem=False, local_knowledge=False, web_search=False)
        # Probe/reconnect on demand so /health reflects current runtime, not only startup snapshot.
        if self.settings.mcp.mode in {"managed", "hybrid"}:
            self._try_start_filesystem()
            self._try_start_local_knowledge()
            self._try_start_web_search()
        return MCPHealth(
            filesystem=self._is_running(self._filesystem_client),
            local_knowledge=self._is_running(self._local_knowledge_client),
            web_search=self._is_running(self._web_search_client),
        )

    def list_files(self, directory: Path) -> str:
        client = self._ensure_filesystem_client()
        ok, value, err = call_with_timeout(lambda: client.list_directory(directory), timeout_s=self._operation_timeout_s)
        if ok:
            return str(value)
        client = self._restart_filesystem_client()
        ok, value, err2 = call_with_timeout(lambda: client.list_directory(directory), timeout_s=self._operation_timeout_s)
        if ok:
            return str(value)
        raise MCPManagerError(f"filesystem list timeout_or_error: {err2 or err}")

    def read_file(self, file_path: Path) -> str:
        client = self._ensure_filesystem_client()
        ok, value, err = call_with_timeout(lambda: client.read_file(file_path), timeout_s=self._operation_timeout_s)
        if ok:
            return str(value)
        client = self._restart_filesystem_client()
        ok, value, err2 = call_with_timeout(lambda: client.read_file(file_path), timeout_s=self._operation_timeout_s)
        if ok:
            return str(value)
        raise MCPManagerError(f"filesystem read timeout_or_error: {err2 or err}")

    def ingest_langchain_docs(self, seed_url: str, max_pages: int, collection: str) -> dict[str, Any]:
        client = self._ensure_local_knowledge_client()
        ok, value, err = call_with_timeout(
            lambda: client.ingest_langchain_docs(seed_url=seed_url, max_pages=max_pages, collection=collection),
            timeout_s=self._operation_timeout_s,
        )
        if ok and isinstance(value, dict):
            return value
        client = self._restart_local_knowledge_client()
        ok, value, err2 = call_with_timeout(
            lambda: client.ingest_langchain_docs(seed_url=seed_url, max_pages=max_pages, collection=collection),
            timeout_s=self._operation_timeout_s,
        )
        if ok and isinstance(value, dict):
            return value
        raise MCPManagerError(f"local_knowledge ingest timeout_or_error: {err2 or err}")

    def search_langchain_docs(self, query: str, top_k: int, collection: str) -> dict[str, Any]:
        client = self._ensure_local_knowledge_client()
        ok, value, err = call_with_timeout(
            lambda: client.search_langchain_docs(query=query, top_k=top_k, collection=collection),
            timeout_s=self._operation_timeout_s,
        )
        if ok and isinstance(value, dict):
            return value
        client = self._restart_local_knowledge_client()
        ok, value, err2 = call_with_timeout(
            lambda: client.search_langchain_docs(query=query, top_k=top_k, collection=collection),
            timeout_s=self._operation_timeout_s,
        )
        if ok and isinstance(value, dict):
            return value
        raise MCPManagerError(f"local_knowledge search timeout_or_error: {err2 or err}")

    def web_search(self, query: str, max_results: int, search_depth: str) -> dict[str, Any]:
        client = self._ensure_web_search_client()
        ok, value, err = call_with_timeout(
            lambda: client.search(query=query, max_results=max_results, search_depth=search_depth),
            timeout_s=self._operation_timeout_s,
        )
        if ok and isinstance(value, dict):
            return value
        client = self._restart_web_search_client()
        ok, value, err2 = call_with_timeout(
            lambda: client.search(query=query, max_results=max_results, search_depth=search_depth),
            timeout_s=self._operation_timeout_s,
        )
        if ok and isinstance(value, dict):
            return value
        raise MCPManagerError(f"web_search timeout_or_error: {err2 or err}")

    def invoke_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not tool.strip():
            raise MCPManagerError("tool name must not be empty")
        srv = server.strip().lower()
        args = arguments or {}

        if srv == "filesystem":
            client = self._ensure_filesystem_client()
            ok, value, err = call_with_timeout(lambda: client.call_tool(tool, args), timeout_s=self._operation_timeout_s)
            if ok and isinstance(value, dict):
                return value
            client = self._restart_filesystem_client()
            ok, value, err2 = call_with_timeout(lambda: client.call_tool(tool, args), timeout_s=self._operation_timeout_s)
            if ok and isinstance(value, dict):
                return value
            raise MCPManagerError(f"filesystem invoke timeout_or_error: {err2 or err}")

        if srv == "local_knowledge":
            client = self._ensure_local_knowledge_client()
            ok, value, err = call_with_timeout(lambda: client.call_tool(tool, args), timeout_s=self._operation_timeout_s)
            if ok and isinstance(value, dict):
                return value
            client = self._restart_local_knowledge_client()
            ok, value, err2 = call_with_timeout(lambda: client.call_tool(tool, args), timeout_s=self._operation_timeout_s)
            if ok and isinstance(value, dict):
                return value
            raise MCPManagerError(f"local_knowledge invoke timeout_or_error: {err2 or err}")

        if srv == "web_search":
            client = self._ensure_web_search_client()
            ok, value, err = call_with_timeout(lambda: client.call_tool(tool, args), timeout_s=self._operation_timeout_s)
            if ok and isinstance(value, dict):
                return value
            client = self._restart_web_search_client()
            ok, value, err2 = call_with_timeout(lambda: client.call_tool(tool, args), timeout_s=self._operation_timeout_s)
            if ok and isinstance(value, dict):
                return value
            raise MCPManagerError(f"web_search invoke timeout_or_error: {err2 or err}")

        raise MCPManagerError(f"unknown MCP server: {server}")

    def available_tools(self) -> dict[str, list[str]]:
        if self.settings.mcp.mode in {"managed", "hybrid"}:
            self._try_start_filesystem()
            self._try_start_local_knowledge()
            self._try_start_web_search()

        tools: dict[str, list[str]] = {"filesystem": [], "local_knowledge": [], "web_search": []}
        fs = self._filesystem_client
        if self._is_running(fs):
            ok, result, err = call_with_timeout(lambda: fs.list_tools(), timeout_s=self._tools_timeout_s)
            if ok and isinstance(result, list):
                tools["filesystem"] = result
            else:
                tools["filesystem"] = []
                if err:
                    self._startup_errors["filesystem"] = f"tools/list timeout_or_error: {err}"

        lk = self._local_knowledge_client
        if self._is_running(lk):
            ok, result, err = call_with_timeout(lambda: lk.list_tools(), timeout_s=self._tools_timeout_s)
            if ok and isinstance(result, list):
                tools["local_knowledge"] = result
            else:
                tools["local_knowledge"] = []
                if err:
                    self._startup_errors["local_knowledge"] = f"tools/list timeout_or_error: {err}"

        ws = self._web_search_client
        if self._is_running(ws):
            ok, result, err = call_with_timeout(lambda: ws.list_tools(), timeout_s=self._tools_timeout_s)
            if ok and isinstance(result, list):
                tools["web_search"] = result
            else:
                tools["web_search"] = []
                if err:
                    self._startup_errors["web_search"] = f"tools/list timeout_or_error: {err}"

        return tools

    def diagnostics(self) -> dict[str, MCPServerDiagnostic]:
        health = self.health()
        tools = self.available_tools()
        fs_category = _classify_startup_error(self._startup_errors.get("filesystem", ""))
        lk_category = _classify_startup_error(self._startup_errors.get("local_knowledge", ""))
        ws_category = _classify_startup_error(self._startup_errors.get("web_search", ""))
        return {
            "filesystem": MCPServerDiagnostic(
                connected=health.filesystem,
                tools=tools["filesystem"],
                startup_error=self._startup_errors.get("filesystem", ""),
                executable=health.filesystem and len(tools["filesystem"]) > 0,
                executable_detail="ok" if health.filesystem and len(tools["filesystem"]) > 0 else "not executable",
                failure_category=fs_category,
                remediation=_remediation_for("filesystem", fs_category),
                launch_command=self._launch_commands.get("filesystem", []),
                python_executable=sys.executable,
                virtual_env=os.getenv("VIRTUAL_ENV", ""),
            ),
            "local_knowledge": MCPServerDiagnostic(
                connected=health.local_knowledge,
                tools=tools["local_knowledge"],
                startup_error=self._startup_errors.get("local_knowledge", ""),
                executable=health.local_knowledge and len(tools["local_knowledge"]) > 0,
                executable_detail="ok" if health.local_knowledge and len(tools["local_knowledge"]) > 0 else "not executable",
                failure_category=lk_category,
                remediation=_remediation_for("local_knowledge", lk_category),
                launch_command=self._launch_commands.get("local_knowledge", []),
                python_executable=sys.executable,
                virtual_env=os.getenv("VIRTUAL_ENV", ""),
            ),
            "web_search": MCPServerDiagnostic(
                connected=health.web_search,
                tools=tools["web_search"],
                startup_error=self._startup_errors.get("web_search", ""),
                executable=health.web_search and len(tools["web_search"]) > 0,
                executable_detail="ok" if health.web_search and len(tools["web_search"]) > 0 else "not executable",
                failure_category=ws_category,
                remediation=_remediation_for("web_search", ws_category),
                launch_command=self._launch_commands.get("web_search", []),
                python_executable=sys.executable,
                virtual_env=os.getenv("VIRTUAL_ENV", ""),
            ),
        }

    def _is_running(self, client: Any | None) -> bool:
        if client is None:
            return False
        process = getattr(client, "process", None)
        if process is None:
            return False
        return process.poll() is None

    def _ensure_filesystem_client(self) -> FilesystemMCPClient:
        if not self._is_running(self._filesystem_client):
            command = self.settings.mcp.filesystem_server_argv()
            self._filesystem_client = FilesystemMCPClient(
                command=command,
                workspace_root=self.workspace_root,
                env=os.environ.copy(),
            )
            self._launch_commands["filesystem"] = [*command, str(self.workspace_root)]
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
            self._local_knowledge_client = LocalKnowledgeMCPClient(command=command, env=os.environ.copy())
            self._launch_commands["local_knowledge"] = command
            self._local_knowledge_client.start()
        return self._local_knowledge_client

    def _restart_local_knowledge_client(self) -> LocalKnowledgeMCPClient:
        if self._local_knowledge_client is not None:
            self._local_knowledge_client.close()
        self._local_knowledge_client = None
        return self._ensure_local_knowledge_client()

    def _ensure_web_search_client(self) -> WebSearchMCPClient:
        if not self._is_running(self._web_search_client):
            command = self.settings.mcp.web_search_server_argv()
            self._web_search_client = WebSearchMCPClient(command=command, env=os.environ.copy())
            self._launch_commands["web_search"] = command
            self._web_search_client.start()
        return self._web_search_client

    def _restart_web_search_client(self) -> WebSearchMCPClient:
        if self._web_search_client is not None:
            self._web_search_client.close()
        self._web_search_client = None
        return self._ensure_web_search_client()

    def _try_start_filesystem(self) -> None:
        ok, _result, err = call_with_timeout(self._ensure_filesystem_client, timeout_s=self._startup_timeout_s)
        if ok:
            self._startup_errors["filesystem"] = ""
            return
        if self._filesystem_client is not None:
            self._filesystem_client.close()
        self._filesystem_client = None
        self._startup_errors["filesystem"] = str(err)

    def _try_start_local_knowledge(self) -> None:
        ok, _result, err = call_with_timeout(self._ensure_local_knowledge_client, timeout_s=self._startup_timeout_s)
        if ok:
            self._startup_errors["local_knowledge"] = ""
            return
        if self._local_knowledge_client is not None:
            self._local_knowledge_client.close()
        self._local_knowledge_client = None
        self._startup_errors["local_knowledge"] = str(err)

    def _try_start_web_search(self) -> None:
        ok, _result, err = call_with_timeout(self._ensure_web_search_client, timeout_s=self._startup_timeout_s)
        if ok:
            self._startup_errors["web_search"] = ""
            return
        if self._web_search_client is not None:
            self._web_search_client.close()
        self._web_search_client = None
        self._startup_errors["web_search"] = str(err)


def _classify_startup_error(error_text: str) -> str:
    text = error_text.lower()
    if not text:
        return "ok"
    if "timeout after" in text or "timeout waiting" in text:
        return "startup_timeout"
    if "missing tavily api key" in text:
        return "missing_key"
    if "no module named" in text:
        return "missing_binary"
    if "not recognized as an internal or external command" in text or "no such file or directory" in text:
        return "missing_binary"
    if "enotcached" in text or "npm error" in text:
        return "missing_binary"
    if "failed to start" in text:
        return "missing_binary"
    if "closed pipe" in text or "traceback" in text or "mcp error" in text:
        return "server_crash"
    return "server_crash"


def _remediation_for(server: str, category: str) -> str:
    if category == "ok":
        return "No action required."
    if category == "missing_key":
        return "Set TAVILY_API_KEY in .env or environment before starting trace."
    if category == "missing_binary":
        if server == "filesystem":
            return "Install Node.js and verify npx works: `npx --version`."
        if server == "web_search":
            return "Install dependencies (including fastmcp): `pip install -r requirements.txt`."
        return "Verify Python environment and required packages are installed."
    if category == "startup_timeout":
        if server == "local_knowledge":
            return "Increase MCP startup timeout or warm up local knowledge server dependencies."
        return "Increase MCP startup timeout and retry."
    return "Inspect server stderr and launch command, then retry with corrected environment."

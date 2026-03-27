from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from typing import Any


class LocalKnowledgeMCPClientError(RuntimeError):
    pass


class LocalKnowledgeMCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        if not command:
            raise LocalKnowledgeMCPClientError("local knowledge MCP command is empty")
        self.command = command
        self.env = env
        self.process: subprocess.Popen | None = None
        self._next_id = 1
        self._tool_name_cache: set[str] | None = None
        self._io_lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._reader_error: str = ""
        self._request_timeout_s: float = 8.0

    def __enter__(self) -> "LocalKnowledgeMCPClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self.process is not None:
            return
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=self.env,
            )
        except OSError as exc:
            raise LocalKnowledgeMCPClientError(f"failed to start local knowledge MCP server: {exc}") from exc
        self._start_reader()
        self._initialize()

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self._reader_thread = None
        self._reader_error = ""
        self._tool_name_cache = None
        self._messages = queue.Queue()

    def ingest_langchain_docs(self, seed_url: str, max_pages: int, collection: str) -> dict[str, Any]:
        tool_name = self._select_tool_name(("knowledge.ingest_langchain_docs", "ingest_langchain_docs"))
        return self._call_tool(
            tool_name,
            {
                "seed_url": seed_url,
                "max_pages": max_pages,
                "collection": collection,
            },
        )

    def search_langchain_docs(self, query: str, top_k: int, collection: str) -> dict[str, Any]:
        tool_name = self._select_tool_name(("knowledge.search_langchain_docs", "search_langchain_docs"))
        return self._call_tool(
            tool_name,
            {
                "query": query,
                "top_k": top_k,
                "collection": collection,
            },
        )

    def list_tools(self) -> list[str]:
        return sorted(self._list_tool_names())

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._call_tool(tool_name, arguments)

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "trace-code", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})

    def _start_reader(self) -> None:
        self._reader_error = ""
        self._messages = queue.Queue()

        def _reader() -> None:
            assert self.process is not None
            assert self.process.stdout is not None
            try:
                while True:
                    line = self.process.stdout.readline()
                    if not line:
                        stderr = ""
                        if self.process.stderr is not None:
                            stderr = self.process.stderr.read().strip()
                        self._reader_error = (stderr or "local knowledge MCP closed stdout").strip()
                        return
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._messages.put(message)
            except Exception as exc:
                self._reader_error = str(exc)

        self._reader_thread = threading.Thread(target=_reader, daemon=True)
        self._reader_thread.start()

    def _list_tool_names(self) -> set[str]:
        if self._tool_name_cache is not None:
            return self._tool_name_cache
        response = self._request("tools/list", {})
        tools = response.get("tools", [])
        names = {tool.get("name") for tool in tools if isinstance(tool, dict) and tool.get("name")}
        self._tool_name_cache = names
        return names

    def _select_tool_name(self, candidates: tuple[str, ...]) -> str:
        names = self._list_tool_names()
        for name in candidates:
            if name in names:
                return name
        wanted = ", ".join(candidates)
        available = ", ".join(sorted(names)) if names else "(none)"
        raise LocalKnowledgeMCPClientError(f"local knowledge MCP missing tool(s): {wanted}; available: {available}")

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        if response.get("isError"):
            raise LocalKnowledgeMCPClientError(f"tool call failed for {tool_name}")

        structured = response.get("structuredContent")
        if isinstance(structured, dict):
            return structured

        content = response.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if not text:
                        continue
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        return {"status": "ok", "results": [], "text": text}
                    if isinstance(parsed, dict):
                        return parsed

        raise LocalKnowledgeMCPClientError("local knowledge MCP response did not contain structured results")

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._io_lock:
            request_id = self._next_id
            self._next_id += 1
            payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            self._write(payload)
            response = self._read_matching_response(request_id, timeout_s=self._request_timeout_s)
        if "error" in response:
            raise LocalKnowledgeMCPClientError(f"MCP error for {method}: {response['error']}")
        if "result" not in response:
            raise LocalKnowledgeMCPClientError(f"missing MCP result for {method}")
        return response["result"]

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write(payload)

    def _write(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise LocalKnowledgeMCPClientError("local knowledge MCP process not running")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def _read_matching_response(self, request_id: int, *, timeout_s: float) -> dict[str, Any]:
        if self.process is None:
            raise LocalKnowledgeMCPClientError("local knowledge MCP process not running")
        deadline = time.monotonic() + timeout_s
        while True:
            if self._reader_error:
                raise LocalKnowledgeMCPClientError(
                    f"local knowledge MCP server closed pipe. {self._reader_error}".strip()
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LocalKnowledgeMCPClientError(f"timeout waiting for MCP response id={request_id}")
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise LocalKnowledgeMCPClientError(f"timeout waiting for MCP response id={request_id}") from exc
            if message.get("id") == request_id:
                return message

from __future__ import annotations

import json
import subprocess
from typing import Any


class WebSearchMCPClientError(RuntimeError):
    pass


class WebSearchMCPClient:
    def __init__(self, command: list[str]):
        if not command:
            raise WebSearchMCPClientError("web search MCP command is empty")
        self.command = command
        self.process: subprocess.Popen | None = None
        self._next_id = 1
        self._tool_name_cache: set[str] | None = None

    def __enter__(self) -> "WebSearchMCPClient":
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
            )
        except OSError as exc:
            raise WebSearchMCPClientError(f"failed to start web search MCP server: {exc}") from exc
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

    def search(self, query: str, max_results: int = 5, search_depth: str = "basic") -> dict[str, Any]:
        tool_name = self._select_tool_name(("web.search", "web_search"))
        return self._call_tool(
            tool_name,
            {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
            },
        )

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
        raise WebSearchMCPClientError(f"web search MCP missing tool(s): {wanted}; available: {available}")

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        if response.get("isError"):
            raise WebSearchMCPClientError(f"tool call failed for {tool_name}")

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
                        return {"status": "ok", "results": [], "answer": text}
                    if isinstance(parsed, dict):
                        return parsed

        raise WebSearchMCPClientError("web search MCP response did not contain structured results")

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self._write(payload)
        response = self._read_matching_response(request_id)
        if "error" in response:
            raise WebSearchMCPClientError(f"MCP error for {method}: {response['error']}")
        if "result" not in response:
            raise WebSearchMCPClientError(f"missing MCP result for {method}")
        return response["result"]

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write(payload)

    def _write(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise WebSearchMCPClientError("web search MCP process not running")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def _read_matching_response(self, request_id: int) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise WebSearchMCPClientError("web search MCP process not running")
        while True:
            line = self.process.stdout.readline()
            if not line:
                stderr = ""
                if self.process.stderr is not None:
                    stderr = self.process.stderr.read().strip()
                raise WebSearchMCPClientError(f"web search MCP server closed pipe. {stderr}".strip())
            message = json.loads(line)
            if message.get("id") == request_id:
                return message

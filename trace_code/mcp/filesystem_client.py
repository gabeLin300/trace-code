from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class MCPClientError(RuntimeError):
    pass


class FilesystemMCPClient:
    def __init__(self, command: list[str], workspace_root: Path, env: dict[str, str] | None = None):
        if not command:
            raise MCPClientError("filesystem MCP command is empty")
        self.command = [*command, str(workspace_root)]
        self.workspace_root = workspace_root
        self.env = env
        self.process: subprocess.Popen | None = None
        self._next_id = 1
        self._tool_name_cache: set[str] | None = None

    def __enter__(self) -> "FilesystemMCPClient":
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
            raise MCPClientError(f"failed to start filesystem MCP server: {exc}") from exc
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

    def list_directory(self, directory_path: Path) -> str:
        tool_name = self._select_tool_name(("list_directory", "listDirectory"))
        result = self._call_tool(tool_name, {"path": str(directory_path)})
        return _tool_result_text(result)

    def read_file(self, file_path: Path) -> str:
        tool_name = self._select_tool_name(("read_file", "readFile"))
        result = self._call_tool(tool_name, {"path": str(file_path)})
        return _tool_result_text(result)

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._call_tool(tool_name, arguments)

    def list_tools(self) -> list[str]:
        return sorted(self._list_tool_names())

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
        raise MCPClientError(f"filesystem MCP missing tool(s): {wanted}; available: {available}")

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        if response.get("isError"):
            raise MCPClientError(f"tool call failed for {tool_name}")
        return response

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self._write(payload)
        response = self._read_matching_response(request_id)
        if "error" in response:
            raise MCPClientError(f"MCP error for {method}: {response['error']}")
        if "result" not in response:
            raise MCPClientError(f"missing MCP result for {method}")
        return response["result"]

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write(payload)

    def _write(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise MCPClientError("filesystem MCP process not running")
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def _read_matching_response(self, request_id: int) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise MCPClientError("filesystem MCP process not running")
        while True:
            line = self.process.stdout.readline()
            if not line:
                stderr = ""
                if self.process.stderr is not None:
                    stderr = self.process.stderr.read().strip()
                raise MCPClientError(f"filesystem MCP server closed pipe. {stderr}".strip())
            message = json.loads(line)
            if message.get("id") == request_id:
                return message


def _tool_result_text(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if text:
                    texts.append(text)
        if texts:
            return "\n".join(texts)
    structured = result.get("structuredContent")
    if structured is not None:
        return json.dumps(structured, ensure_ascii=True, indent=2)
    raise MCPClientError("filesystem MCP response did not contain text content")

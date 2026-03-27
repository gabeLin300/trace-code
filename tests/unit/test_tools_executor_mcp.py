from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.mcp.filesystem_client import MCPClientError
from trace_code.tools import executor


class _FakeClient:
    def __init__(self, command, workspace_root):
        self.command = command
        self.workspace_root = workspace_root

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def list_directory(self, directory_path: Path) -> str:
        return "a.py\nb.py"

    def read_file(self, file_path: Path) -> str:
        return "file-content"


class _FailingClient:
    def __init__(self, command, workspace_root):
        pass

    def __enter__(self):
        raise MCPClientError("no server")

    def __exit__(self, exc_type, exc, tb):
        return None


def test_list_files_prefers_mcp(monkeypatch, tmp_path) -> None:
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(executor, "FilesystemMCPClient", _FakeClient)

    result = executor.execute_tool_from_prompt(
        "list files",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "fs.list"
    assert result["output"] == "a.py\nb.py"


def test_read_file_prefers_mcp(monkeypatch, tmp_path) -> None:
    (tmp_path / "data.txt").write_text("local-data", encoding="utf-8")
    monkeypatch.setattr(executor, "FilesystemMCPClient", _FakeClient)

    result = executor.execute_tool_from_prompt(
        "read file data.txt",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "fs.read"
    assert result["output"] == "file-content"


def test_read_shorthand_prefers_mcp(monkeypatch, tmp_path) -> None:
    (tmp_path / "README.md").write_text("local-data", encoding="utf-8")
    monkeypatch.setattr(executor, "FilesystemMCPClient", _FakeClient)

    result = executor.execute_tool_from_prompt(
        "read README.md",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "fs.read"
    assert result["output"] == "file-content"


def test_falls_back_to_local_when_mcp_unavailable(monkeypatch, tmp_path) -> None:
    (tmp_path / "fallback.txt").write_text("fallback-data", encoding="utf-8")
    monkeypatch.setattr(executor, "FilesystemMCPClient", _FailingClient)

    list_result = executor.execute_tool_from_prompt(
        "list files",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )
    read_result = executor.execute_tool_from_prompt(
        "read file fallback.txt",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert "fallback.txt" in list_result["output"]
    assert read_result["output"] == "fallback-data"

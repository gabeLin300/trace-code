from pathlib import Path

import pytest

from trace_code.tools.executor import execute_tool_call


def test_structured_fs_write_and_read(tmp_path: Path) -> None:
    write = execute_tool_call(
        tool_name="fs.write",
        arguments={"path": "notes/demo.txt", "content": "hello world"},
        workspace_root=tmp_path,
    )
    assert write["status"] == "ok"

    read = execute_tool_call(
        tool_name="fs.read",
        arguments={"path": "notes/demo.txt"},
        workspace_root=tmp_path,
    )
    assert read["status"] == "ok"
    assert read["output"] == "hello world"


def test_structured_fs_edit(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha beta gamma", encoding="utf-8")
    result = execute_tool_call(
        tool_name="fs.edit",
        arguments={"path": "a.txt", "find": "beta", "replace": "BETA"},
        workspace_root=tmp_path,
    )
    assert result["status"] == "ok"
    assert "BETA" in (tmp_path / "a.txt").read_text(encoding="utf-8")


def test_structured_fs_search_code(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("def hello_world():\n    return 1\n", encoding="utf-8")
    result = execute_tool_call(
        tool_name="fs.search_code",
        arguments={"query": "hello_world"},
        workspace_root=tmp_path,
    )
    assert result["status"] == "ok"
    assert "hello_world" in result["output"]


def test_structured_unknown_tool_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="unsupported tool name"):
        execute_tool_call(
            tool_name="unknown.tool",
            arguments={},
            workspace_root=tmp_path,
        )


def test_tool_alias_normalization(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    result = execute_tool_call(
        tool_name="filesystem_read",
        arguments={"path": "a.txt"},
        workspace_root=tmp_path,
    )
    assert result["tool_name"] == "fs.read"
    assert result["output"] == "hello"


def test_structured_mcp_call_with_dynamic_tool(tmp_path: Path) -> None:
    class _FakeMCPManager:
        def invoke_tool(self, server: str, tool: str, arguments: dict):
            assert server == "filesystem"
            assert tool == "custom.echo"
            assert arguments == {"value": "ok"}
            return {"structuredContent": {"echo": "ok"}}

    result = execute_tool_call(
        tool_name="mcp.call",
        arguments={"server": "filesystem", "tool": "custom.echo", "arguments": {"value": "ok"}},
        workspace_root=tmp_path,
        mcp_manager=_FakeMCPManager(),
    )
    assert result["status"] == "ok"
    assert result["tool_name"] == "mcp.call"
    assert '"echo": "ok"' in result["output"]

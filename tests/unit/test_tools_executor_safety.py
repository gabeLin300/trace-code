import subprocess

from trace_code.config import TraceSettings
from trace_code.tools import executor


def test_shell_blocked_command_returns_blocked_status(tmp_path) -> None:
    result = executor.execute_tool_from_prompt(
        "run command rm -rf /",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["tool_name"] == "shell.exec"
    assert result["status"] == "blocked"


def test_shell_non_read_requires_confirmation_by_default(tmp_path) -> None:
    result = executor.execute_tool_from_prompt(
        "run command touch x.txt",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["status"] == "requires_confirmation"
    assert "confirm run command" in result["output"]


def test_shell_non_read_runs_when_confirmed(monkeypatch, tmp_path) -> None:
    class _Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _Completed())

    result = executor.execute_tool_from_prompt(
        "confirm run command touch x.txt",
        workspace_root=tmp_path,
        settings=TraceSettings(workspace_root=tmp_path),
    )

    assert result["status"] == "ok"
    assert result["tool_name"] == "shell.exec"


def test_shell_non_read_blocked_in_read_only_mode(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    settings.safety.read_only = True

    result = executor.execute_tool_from_prompt(
        "confirm run command touch x.txt",
        workspace_root=tmp_path,
        settings=settings,
    )

    assert result["status"] == "blocked"

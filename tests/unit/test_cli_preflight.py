from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trace_code.cli import preflight
from trace_code.config import TraceSettings


@dataclass
class _Diag:
    executable: bool
    startup_error: str
    remediation: str


class _FakeManager:
    def __init__(self, settings, workspace_root):
        self.settings = settings
        self.workspace_root = workspace_root

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None

    def diagnostics(self):
        return {
            "filesystem": _Diag(True, "", "No action required."),
            "local_knowledge": _Diag(True, "", "No action required."),
            "web_search": _Diag(True, "", "No action required."),
        }


def test_run_preflight_passes_when_keys_and_mcp_are_available(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(preflight.shutil, "which", lambda name: "C:\\npx.cmd")
    monkeypatch.setattr(preflight, "MCPManager", _FakeManager)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")

    report = preflight.run_preflight(TraceSettings(workspace_root=tmp_path))
    assert report.ok is True
    assert "Preflight result: PASS" in report.render()


def test_run_preflight_fails_with_actionable_output(monkeypatch, tmp_path: Path) -> None:
    class _FailManager(_FakeManager):
        def diagnostics(self):
            return {
                "filesystem": _Diag(False, "missing executable", "Install Node.js and verify with: npx --version"),
                "local_knowledge": _Diag(True, "", "No action required."),
                "web_search": _Diag(False, "Missing Tavily API key", "Set TAVILY_API_KEY in .env"),
            }

    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)
    monkeypatch.setattr(preflight, "MCPManager", _FailManager)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    report = preflight.run_preflight(TraceSettings(workspace_root=tmp_path))
    text = report.render()
    assert report.ok is False
    assert "[FAIL] dependency.npx" in text
    assert "fix:" in text
    assert "Preflight result: FAIL" in text

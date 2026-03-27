from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.config_init import required_api_keys
from trace_code.mcp.manager import MCPManager


@dataclass
class PreflightCheck:
    name: str
    ok: bool
    detail: str
    remediation: str


@dataclass
class PreflightReport:
    checks: list[PreflightCheck]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.checks)

    def render(self) -> str:
        lines: list[str] = []
        for item in self.checks:
            status = "PASS" if item.ok else "FAIL"
            lines.append(f"[{status}] {item.name}: {item.detail}")
            if not item.ok and item.remediation:
                lines.append(f"  fix: {item.remediation}")
        lines.append("Preflight result: PASS" if self.ok else "Preflight result: FAIL")
        return "\n".join(lines)


def run_preflight(settings: TraceSettings) -> PreflightReport:
    checks: list[PreflightCheck] = []
    checks.append(_check_npx_available(settings))
    checks.extend(_check_required_keys(settings))
    checks.extend(_check_mcp_launchability(settings))
    return PreflightReport(checks=checks)


def _check_npx_available(settings: TraceSettings) -> PreflightCheck:
    argv = settings.mcp.filesystem_server_argv()
    executable = argv[0] if argv else "npx"
    ok = bool(shutil.which(executable) or Path(executable).exists())
    detail = f"filesystem MCP executable resolved to '{executable}'" if ok else f"filesystem MCP executable not found: '{executable}'"
    remediation = "Install Node.js and verify with: npx --version"
    return PreflightCheck(name="dependency.npx", ok=ok, detail=detail, remediation=remediation)


def _check_required_keys(settings: TraceSettings) -> list[PreflightCheck]:
    checks: list[PreflightCheck] = []
    for key in required_api_keys(settings):
        value = os.getenv(key, "").strip()
        ok = bool(value)
        detail = "set" if ok else "missing"
        remediation = f"Set {key} in .env (or environment) before running trace."
        checks.append(PreflightCheck(name=f"env.{key}", ok=ok, detail=detail, remediation=remediation))
    return checks


def _check_mcp_launchability(settings: TraceSettings) -> list[PreflightCheck]:
    manager = MCPManager(settings=settings, workspace_root=Path(settings.workspace_root))
    manager.start()
    diagnostics = manager.diagnostics()
    manager.close()

    checks: list[PreflightCheck] = []
    for server_name in ("filesystem", "local_knowledge", "web_search"):
        item = diagnostics[server_name]
        detail = "launchable with tools discovered" if item.executable else (item.startup_error or "server not executable")
        checks.append(
            PreflightCheck(
                name=f"mcp.{server_name}",
                ok=item.executable,
                detail=detail,
                remediation=item.remediation,
            )
        )
    return checks

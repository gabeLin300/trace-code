from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_code.agent import loop
from trace_code.config import TraceSettings
from trace_code.llm.base import LLMResponse


@pytest.mark.perf
@pytest.mark.parametrize("runs", [5])
def test_representative_command_baseline(
    monkeypatch,
    tmp_path: Path,
    representative_commands,
    perf_results_path: Path,
    runs: int,
) -> None:
    settings = TraceSettings(workspace_root=tmp_path)

    def _needs_tool(user_input: str) -> bool:
        lowered = user_input.lower()
        return (
            "list files" in lowered
            or "read file" in lowered
            or "search web" in lowered
            or "search langchain docs" in lowered
        )

    def _fake_tool(**kwargs):
        prompt = kwargs["user_input"].lower()
        if "list files" in prompt:
            return {"tool_name": "fs.list", "status": "ok", "output": "README.md\ntrace_code"}
        if "read file" in prompt:
            return {"tool_name": "fs.read", "status": "ok", "output": "# Trace Code\n"}
        if "search web" in prompt:
            return {"tool_name": "web.search", "status": "ok", "output": "LangChain latest is 1.2.13"}
        if "search langchain docs" in prompt:
            return {
                "tool_name": "knowledge.search_langchain_docs",
                "status": "ok",
                "output": "Use retrieval chains for retrieval-augmented generation.",
            }
        return {"tool_name": "unknown", "status": "ok", "output": "ok"}

    def _fake_generate(self, prompt: str, provider_override=None):
        # First planning step for tool-oriented prompts gets forced to a tool call by loop logic.
        if "Stage: first" in prompt:
            return LLMResponse(
                provider="groq",
                model="llama-3.3-70b-versatile",
                content="FINAL: planning",
            )
        return LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content="FINAL: completed",
        )

    monkeypatch.setattr(loop, "prompt_requests_tool", _needs_tool)
    monkeypatch.setattr(loop, "execute_tool_from_prompt", _fake_tool)
    monkeypatch.setattr(loop.LLMManager, "generate", _fake_generate)

    lines: list[str] = []
    for command in representative_commands:
        for run_idx in range(1, runs + 1):
            result = loop.run_agentic_task(
                command.prompt,
                settings=settings,
                mcp_manager=None,
                max_steps=4,
            )
            entry = {
                "command": command.name,
                "prompt": command.prompt,
                "run": run_idx,
                "status": result.get("status"),
                "stop_reason": result.get("stop_reason"),
                "perf": result.get("perf", []),
            }
            lines.append(json.dumps(entry, ensure_ascii=True))

    perf_results_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert perf_results_path.exists()
    assert perf_results_path.stat().st_size > 0

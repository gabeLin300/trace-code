from trace_code.agent import loop
from trace_code.llm.base import LLMResponse


def test_agent_completes_multi_step_task_autonomously(monkeypatch) -> None:
    commands_seen: list[str] = []

    def _fake_execute_tool_from_prompt(**kwargs):
        user_input = kwargs["user_input"]
        commands_seen.append(user_input)
        if len(commands_seen) == 1:
            return {"tool_name": "fs.list", "status": "ok", "output": "README.md\na.py"}
        return {"tool_name": "fs.read", "status": "ok", "output": "def greet():\n    return 'hi'"}

    monkeypatch.setattr(loop, "execute_tool_from_prompt", _fake_execute_tool_from_prompt)
    monkeypatch.setattr(loop, "prompt_requests_tool", lambda _text: True)

    llm_outputs = iter(
        [
            "TOOL: list files",
            "TOOL: read file a.py",
            "FINAL: I inspected the workspace and confirmed a.py defines greet returning hi.",
        ]
    )
    monkeypatch.setattr(
        loop.LLMManager,
        "generate",
        lambda self, prompt, provider_override=None: LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content=next(llm_outputs),
        ),
    )

    result = loop.run_agentic_task("Find and inspect the greet implementation.", max_steps=5)

    assert result["status"] == "answered_with_tools"
    assert len(result["tools"]) >= 2
    assert result["completion"]["is_complete"] is True
    assert result["completion"]["confidence"] in {"medium", "high"}

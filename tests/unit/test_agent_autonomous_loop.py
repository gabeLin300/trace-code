from trace_code.agent import loop
from trace_code.llm.base import LLMResponse


def test_run_agentic_task_answers_without_tools(monkeypatch) -> None:
    monkeypatch.setattr(loop, "prompt_requests_tool", lambda _text: False)
    monkeypatch.setattr(
        loop.LLMManager,
        "generate",
        lambda self, prompt, provider_override=None: LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content="direct answer",
        ),
    )

    result = loop.run_agentic_task("Explain this codebase.")

    assert result["status"] == "answered"
    assert result["response"] == "direct answer"
    assert result["tools"] == []
    assert result["stop_reason"] == "done"


def test_run_agentic_task_executes_tool_then_finalizes(monkeypatch) -> None:
    monkeypatch.setattr(loop, "prompt_requests_tool", lambda _text: True)
    monkeypatch.setattr(
        loop,
        "execute_tool_from_prompt",
        lambda **kwargs: {
            "tool_name": "fs.list",
            "status": "ok",
            "output": "README.md\ntrace_code",
        },
    )
    monkeypatch.setattr(
        loop.LLMManager,
        "generate",
        lambda self, prompt, provider_override=None: LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content="FINAL: I checked the workspace and found the main project files.",
        ),
    )

    result = loop.run_agentic_task("List files and summarize.")

    assert result["status"] == "answered_with_tools"
    assert result["tools"][0]["tool_name"] == "fs.list"
    assert result["tools"][0]["status"] == "tool_called"
    assert "main project files" in result["response"]
    assert result["stop_reason"] == "done"


def test_run_agentic_task_can_chain_tool_steps(monkeypatch) -> None:
    monkeypatch.setattr(loop, "prompt_requests_tool", lambda text: "read file" in text.lower() or "list files" in text.lower())
    commands_seen: list[str] = []

    def _fake_execute_tool_from_prompt(**kwargs):
        user_input = kwargs["user_input"]
        commands_seen.append(user_input)
        if len(commands_seen) == 1:
            return {"tool_name": "fs.list", "status": "ok", "output": "a.py\nb.py"}
        return {"tool_name": "fs.read", "status": "ok", "output": "print('hello')"}

    monkeypatch.setattr(loop, "execute_tool_from_prompt", _fake_execute_tool_from_prompt)

    llm_outputs = iter(
        [
            "TOOL: list files",
            "TOOL: read file a.py",
            "FINAL: I listed files then read a.py. It prints hello.",
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

    result = loop.run_agentic_task("Inspect files and read the first file.", max_steps=4)

    assert result["status"] == "answered_with_tools"
    assert len(result["tools"]) == 2
    assert commands_seen[1] == "read file a.py"
    assert result["stop_reason"] == "done"


def test_run_agentic_task_can_select_tool_from_model_decision(monkeypatch) -> None:
    monkeypatch.setattr(loop, "prompt_requests_tool", lambda text: "list files" in text.lower())
    commands_seen: list[str] = []

    def _fake_execute_tool_from_prompt(**kwargs):
        commands_seen.append(kwargs["user_input"])
        return {"tool_name": "fs.list", "status": "ok", "output": "README.md"}

    monkeypatch.setattr(loop, "execute_tool_from_prompt", _fake_execute_tool_from_prompt)

    llm_outputs = iter(
        [
            "TOOL: list files",
            "FINAL: I listed files and found README.md",
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

    result = loop.run_agentic_task("Can you inspect the workspace?")

    assert result["status"] == "answered_with_tools"
    assert commands_seen == ["list files"]
    assert result["tools"][0]["tool_name"] == "fs.list"
    assert result["stop_reason"] == "done"


def test_run_agentic_task_ignores_unsupported_tool_decision(monkeypatch) -> None:
    monkeypatch.setattr(loop, "prompt_requests_tool", lambda _text: False)
    monkeypatch.setattr(
        loop.LLMManager,
        "generate",
        lambda self, prompt, provider_override=None: LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content="TOOL: think about response",
        ),
    )

    result = loop.run_agentic_task("hi")

    assert result["status"] == "answered"
    assert result["response"] == "think about response"
    assert result["tools"] == []
    assert result["stop_reason"] == "done"


def test_run_agentic_task_stops_on_repeated_tool_guardrail(monkeypatch) -> None:
    monkeypatch.setattr(loop, "prompt_requests_tool", lambda _text: True)
    monkeypatch.setattr(
        loop,
        "execute_tool_from_prompt",
        lambda **kwargs: {"tool_name": "fs.list", "status": "ok", "output": "README.md"},
    )
    llm_outputs = iter(["TOOL: list files", "TOOL: list files", "TOOL: list files"])
    monkeypatch.setattr(
        loop.LLMManager,
        "generate",
        lambda self, prompt, provider_override=None: LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content=next(llm_outputs),
        ),
    )

    result = loop.run_agentic_task("list files repeatedly", max_steps=4)

    assert result["status"] == "no_progress"
    assert result["stop_reason"] in {"repeated_tool", "no_progress"}

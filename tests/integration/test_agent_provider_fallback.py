from trace_code.agent.loop import run_turn
import trace_code.agent.loop as loop
from trace_code.config import TraceSettings
from trace_code.llm.base import LLMResponse, ProviderError
from trace_code.llm.manager import LLMManager


def test_run_turn_uses_default_provider_path(monkeypatch) -> None:
    monkeypatch.setattr(
        LLMManager,
        "generate",
        lambda self, prompt, provider_override=None: LLMResponse(
            provider="groq",
            model="llama-3.3-70b-versatile",
            content=f"ok:{prompt}",
        ),
    )
    result = run_turn("explain this function", wants_tool=False, settings=TraceSettings())
    assert result["status"] == "answered"
    assert result["provider"] == "groq"


def test_run_turn_falls_back_to_groq_when_default_fails(monkeypatch) -> None:
    def _generate(self, prompt, provider_override=None):
        return LLMResponse(provider="groq", model="llama-3.1-8b-instant", content=f"ok:{prompt}")

    monkeypatch.setattr(LLMManager, "generate", _generate)
    result = run_turn("explain this function", wants_tool=False, settings=TraceSettings())
    assert result["status"] == "answered"
    assert result["provider"] == "groq"


def test_run_turn_returns_error_when_disabled_provider_selected(monkeypatch) -> None:
    def _raise(self, prompt, provider_override=None):
        raise ProviderError("provider disabled: openai")

    monkeypatch.setattr(LLMManager, "generate", _raise)
    result = run_turn(
        "explain",
        wants_tool=False,
        settings=TraceSettings(),
        provider_override="openai:gpt-4o-mini",
    )
    assert result["status"] == "error"
    assert "provider disabled: openai" in result["response"]


def test_run_turn_uses_augmented_prompt_for_llm_path(monkeypatch) -> None:
    monkeypatch.setattr(
        loop,
        "build_augmented_prompt",
        lambda user_input, settings, workspace_root, mcp_manager=None: f"AUG::{user_input}",
    )

    captured = {}

    def _generate(self, prompt, provider_override=None):
        captured["prompt"] = prompt
        return LLMResponse(provider="groq", model="llama-3.3-70b-versatile", content="ok")

    monkeypatch.setattr(LLMManager, "generate", _generate)

    result = run_turn("explain map-reduce chain", wants_tool=False, settings=TraceSettings())

    assert result["status"] == "answered"
    assert captured["prompt"] == "AUG::explain map-reduce chain"

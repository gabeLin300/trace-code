import pytest

from trace_code.config import TraceSettings
from trace_code.llm.base import LLMResponse, ProviderError, ProviderSelectionError
from trace_code.llm.manager import LLMManager, parse_provider_route


def test_parse_provider_route() -> None:
    route = parse_provider_route("groq:llama-3.3-70b-versatile")
    assert route.provider == "groq"
    assert route.model == "llama-3.3-70b-versatile"


def test_default_provider_route_uses_groq(monkeypatch) -> None:
    manager = LLMManager(TraceSettings())
    monkeypatch.setattr(
        manager.providers["groq"], "generate", lambda prompt, model: LLMResponse(provider="groq", model=model, content=f"ok:{prompt}")
    )
    out = manager.generate("hello")
    assert out.provider == "groq"


def test_fallback_to_secondary_groq_model_when_default_fails(monkeypatch) -> None:
    manager = LLMManager(TraceSettings())

    def _raise(prompt, model):
        raise ProviderError("down")

    monkeypatch.setattr(manager.providers["groq"], "generate", _raise)

    calls = {"count": 0}

    def _generate(prompt, model):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ProviderError("default failed")
        return LLMResponse(provider="groq", model=model, content=f"ok:{prompt}")

    monkeypatch.setattr(
        manager.providers["groq"], "generate", _generate
    )
    out = manager.generate("hello")
    assert out.provider == "groq"
    assert "llama-3.1-8b-instant" in out.model


def test_openai_requires_explicit_enablement() -> None:
    manager = LLMManager(TraceSettings())
    with pytest.raises(ProviderSelectionError, match="provider disabled: openai"):
        manager.generate("hello", provider_override="openai:gpt-4o-mini")


def test_generate_stream_uses_default_provider(monkeypatch) -> None:
    manager = LLMManager(TraceSettings())
    monkeypatch.setattr(
        manager.providers["groq"],
        "stream_generate",
        lambda prompt, model: iter(["a", "b", "c"]),
    )
    assert "".join(manager.generate_stream("hello")) == "abc"


def test_generate_stream_falls_back_when_default_fails(monkeypatch) -> None:
    manager = LLMManager(TraceSettings())
    calls = {"count": 0}

    def _stream(prompt, model):
        calls["count"] += 1
        if calls["count"] == 1:
            raise ProviderError("down")
        return iter(["ok"])

    monkeypatch.setattr(manager.providers["groq"], "stream_generate", _stream)
    assert "".join(manager.generate_stream("hello")) == "ok"

from trace_code.config import TraceSettings
from trace_code.llm.base import LLMResponse
from trace_code.llm.manager import LLMManager


def test_provider_contract_defaults_are_declared() -> None:
    s = TraceSettings()
    providers = [
        s.llm.default.split(":", 1)[0],
        s.llm.fallback.split(":", 1)[0],
    ]
    assert "groq" in providers


def test_all_provider_adapters_expose_generate_and_stream() -> None:
    manager = LLMManager(TraceSettings())
    for provider in manager.providers.values():
        assert callable(getattr(provider, "generate"))
        assert callable(getattr(provider, "stream_generate"))


def test_manager_stream_contract_returns_text_chunks(monkeypatch) -> None:
    manager = LLMManager(TraceSettings())
    monkeypatch.setattr(
        manager.providers["groq"],
        "stream_generate",
        lambda prompt, model: iter(["hello", " world"]),
    )
    out = "".join(manager.generate_stream("hi"))
    assert out == "hello world"


def test_manager_sync_and_stream_contract_can_be_combined(monkeypatch) -> None:
    manager = LLMManager(TraceSettings())
    monkeypatch.setattr(
        manager.providers["groq"],
        "generate",
        lambda prompt, model: LLMResponse(provider="groq", model=model, content="sync-ok"),
    )
    monkeypatch.setattr(
        manager.providers["groq"],
        "stream_generate",
        lambda prompt, model: iter(["stream-", "ok"]),
    )
    assert manager.generate("x").content == "sync-ok"
    assert "".join(manager.generate_stream("x")) == "stream-ok"

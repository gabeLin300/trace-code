from trace_code.config import TraceSettings


def test_provider_contract_defaults_are_declared() -> None:
    s = TraceSettings()
    providers = [
        s.llm.default.split(":", 1)[0],
        s.llm.fallback.split(":", 1)[0],
    ]
    assert "groq" in providers

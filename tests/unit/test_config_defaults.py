from trace_code.config import TraceSettings


def test_default_model_route_and_fallbacks() -> None:
    settings = TraceSettings()
    assert settings.llm.default == "ollama:qwen3:8b-instruct"
    assert settings.llm.ollama_fallback == "ollama:qwen3:14b-instruct"
    assert settings.llm.fallback == "groq:openai/gpt-oss-20b"
    assert settings.llm.openai_enabled is False

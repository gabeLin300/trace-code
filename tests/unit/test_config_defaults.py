from trace_code.config import TraceSettings


def test_default_model_route_and_fallbacks() -> None:
    settings = TraceSettings()
    assert settings.llm.default == "groq:llama-3.3-70b-versatile"
    assert settings.llm.ollama_fallback == "ollama:qwen3:14b-instruct"
    assert settings.llm.fallback == "groq:llama-3.1-8b-instant"
    assert settings.llm.openai_enabled is False
    assert settings.web_search.api_key_env_var == "TAVILY_API_KEY"

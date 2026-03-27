from trace_code.config import TraceSettings


def test_default_model_route_and_fallbacks() -> None:
    settings = TraceSettings()
    assert ":" in settings.llm.default
    assert settings.llm.default.split(":", 1)[0] in {"groq", "ollama", "openai"}
    assert settings.llm.ollama_fallback == "ollama:qwen3:14b-instruct"
    assert settings.llm.fallback == "groq:llama-3.1-8b-instant"
    assert settings.llm.openai_enabled is False
    assert settings.web_search.api_key_env_var == "TAVILY_API_KEY"
    assert settings.ui.stream_responses is True
    assert settings.mcp.startup_timeout_s == 8.0

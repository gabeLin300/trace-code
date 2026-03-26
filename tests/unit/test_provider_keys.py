from trace_code.llm.providers import GroqProvider, OpenAIProvider, _clean_api_key


def test_clean_api_key_strips_whitespace_and_quotes() -> None:
    assert _clean_api_key("  abc  ") == "abc"
    assert _clean_api_key('"abc"') == "abc"
    assert _clean_api_key("'abc'") == "abc"


def test_groq_provider_cleans_api_key() -> None:
    provider = GroqProvider(api_key=' "gsk-demo" ')
    assert provider.api_key == "gsk-demo"


def test_openai_provider_cleans_api_key() -> None:
    provider = OpenAIProvider(api_key=" 'sk-demo' ")
    assert provider.api_key == "sk-demo"

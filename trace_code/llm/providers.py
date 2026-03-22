from __future__ import annotations

import json
import os
from urllib import error, request

from trace_code.llm.base import LLMProvider, LLMResponse, ProviderError


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")

    def generate(self, prompt: str, model: str) -> LLMResponse:
        url = f"{self.base_url}/api/generate"
        body = {"model": model, "prompt": prompt, "stream": False}
        payload = _post_json(url=url, body=body, api_key=None)
        content = payload.get("response", "")
        if not content:
            raise ProviderError("ollama returned an empty response")
        return LLMResponse(
            provider=self.name,
            model=model,
            content=content,
        )


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.base_url = (base_url or os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")).rstrip("/")

    def generate(self, prompt: str, model: str) -> LLMResponse:
        if not self.api_key:
            raise ProviderError("missing GROQ_API_KEY")
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        payload = _post_json(url=url, body=body, api_key=self.api_key)
        content = _extract_chat_content(payload)
        return LLMResponse(
            provider=self.name,
            model=model,
            content=content,
        )


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")

    def generate(self, prompt: str, model: str) -> LLMResponse:
        if not self.api_key:
            raise ProviderError("missing OPENAI_API_KEY")
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        payload = _post_json(url=url, body=body, api_key=self.api_key)
        content = _extract_chat_content(payload)
        return LLMResponse(
            provider=self.name,
            model=model,
            content=content,
        )


def _post_json(url: str, body: dict, api_key: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderError(f"request failed for {url}: {exc}") from exc


def _extract_chat_content(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("chat completion response missing choices")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not content:
        raise ProviderError("chat completion response missing content")
    return content

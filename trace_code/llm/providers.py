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

    def stream_generate(self, prompt: str, model: str):
        url = f"{self.base_url}/api/generate"
        body = {"model": model, "prompt": prompt, "stream": True}
        req = request.Request(
            url=url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "trace-code/0.1",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                while True:
                    line = response.readline()
                    if not line:
                        break
                    try:
                        payload = json.loads(line.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
                    chunk = str(payload.get("response", ""))
                    if chunk:
                        yield chunk
        except error.HTTPError as exc:
            raise ProviderError(f"request failed for {url}: HTTP {exc.code}") from exc
        except (error.URLError, TimeoutError) as exc:
            raise ProviderError(f"request failed for {url}: {exc}") from exc


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = _clean_api_key(api_key or os.getenv("GROQ_API_KEY"))
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

    def stream_generate(self, prompt: str, model: str):
        if not self.api_key:
            raise ProviderError("missing GROQ_API_KEY")
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "stream": True,
        }
        yield from _stream_openai_compatible(url=url, body=body, api_key=self.api_key)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = _clean_api_key(api_key or os.getenv("OPENAI_API_KEY"))
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

    def stream_generate(self, prompt: str, model: str):
        if not self.api_key:
            raise ProviderError("missing OPENAI_API_KEY")
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "stream": True,
        }
        yield from _stream_openai_compatible(url=url, body=body, api_key=self.api_key)


def _post_json(url: str, body: dict, api_key: str | None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "trace-code/0.1",
    }
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
    except error.HTTPError as exc:
        details = ""
        try:
            details = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            details = ""
        hint = ""
        if exc.code in {401, 403}:
            hint = " (auth failed: verify API key, provider account access, and model permission)"
        msg = f"request failed for {url}: HTTP {exc.code}{hint}"
        if details:
            msg = f"{msg}; {details}"
        raise ProviderError(msg) from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
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


def _clean_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip()
    if len(key) >= 2 and ((key[0] == '"' and key[-1] == '"') or (key[0] == "'" and key[-1] == "'")):
        key = key[1:-1].strip()
    return key or None


def _stream_openai_compatible(*, url: str, body: dict, api_key: str):
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "trace-code/0.1",
    }
    req = request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            for payload in _iter_sse_json(response):
                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                delta = choices[0].get("delta", {}) or {}
                chunk = delta.get("content", "")
                if chunk:
                    yield str(chunk)
    except error.HTTPError as exc:
        details = ""
        try:
            details = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            details = ""
        hint = ""
        if exc.code in {401, 403}:
            hint = " (auth failed: verify API key, provider account access, and model permission)"
        msg = f"request failed for {url}: HTTP {exc.code}{hint}"
        if details:
            msg = f"{msg}; {details}"
        raise ProviderError(msg) from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderError(f"request failed for {url}: {exc}") from exc


def _iter_sse_json(response):
    while True:
        line = response.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text.startswith("data:"):
            continue
        data = text[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload

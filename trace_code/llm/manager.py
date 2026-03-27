from __future__ import annotations

from dataclasses import dataclass

from trace_code.config import TraceSettings
from trace_code.llm.base import ProviderError, ProviderSelectionError
from trace_code.llm.providers import GroqProvider, OllamaProvider, OpenAIProvider


@dataclass
class Route:
    provider: str
    model: str


def parse_provider_route(route: str) -> Route:
    provider, model = route.split(":", 1)
    return Route(provider=provider, model=model)


class LLMManager:
    def __init__(self, settings: TraceSettings):
        self.settings = settings
        self.providers = {
            "ollama": OllamaProvider(),
            "groq": GroqProvider(),
            "openai": OpenAIProvider(),
        }

    def _is_enabled(self, provider: str) -> bool:
        if provider == "openai":
            return self.settings.llm.openai_enabled
        return True

    def _resolve(self, provider: str):
        if provider not in self.providers:
            raise ProviderSelectionError(f"unknown provider: {provider}")
        if not self._is_enabled(provider):
            raise ProviderSelectionError(f"provider disabled: {provider}")
        return self.providers[provider]

    def generate(self, prompt: str, provider_override: str | None = None):
        if provider_override:
            route = parse_provider_route(provider_override)
            provider = self._resolve(route.provider)
            return provider.generate(prompt, route.model)

        default_route = parse_provider_route(self.settings.llm.default)
        fallback_route = parse_provider_route(self.settings.llm.fallback)

        default_err: ProviderError | None = None
        try:
            provider = self._resolve(default_route.provider)
            return provider.generate(prompt, default_route.model)
        except ProviderError as exc:
            default_err = exc
        try:
            fallback_provider = self._resolve(fallback_route.provider)
            return fallback_provider.generate(prompt, fallback_route.model)
        except ProviderError as fallback_err:
            default_msg = str(default_err) if default_err is not None else "unknown"
            raise ProviderError(
                "both default and fallback providers failed: "
                f"default={default_route.provider}:{default_route.model} -> {default_msg}; "
                f"fallback={fallback_route.provider}:{fallback_route.model} -> {fallback_err}"
            ) from fallback_err

    def generate_stream(self, prompt: str, provider_override: str | None = None):
        if provider_override:
            route = parse_provider_route(provider_override)
            provider = self._resolve(route.provider)
            yield from provider.stream_generate(prompt, route.model)
            return

        default_route = parse_provider_route(self.settings.llm.default)
        fallback_route = parse_provider_route(self.settings.llm.fallback)

        default_err: ProviderError | None = None
        try:
            provider = self._resolve(default_route.provider)
            yield from provider.stream_generate(prompt, default_route.model)
            return
        except ProviderError as exc:
            default_err = exc

        try:
            fallback_provider = self._resolve(fallback_route.provider)
            yield from fallback_provider.stream_generate(prompt, fallback_route.model)
        except ProviderError as fallback_err:
            default_msg = str(default_err) if default_err is not None else "unknown"
            raise ProviderError(
                "both default and fallback providers failed: "
                f"default={default_route.provider}:{default_route.model} -> {default_msg}; "
                f"fallback={fallback_route.provider}:{fallback_route.model} -> {fallback_err}"
            ) from fallback_err

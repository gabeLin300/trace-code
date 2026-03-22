from __future__ import annotations

from dataclasses import dataclass


class ProviderError(RuntimeError):
    pass


class ProviderSelectionError(ValueError):
    pass


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    provider: str
    model: str
    content: str


class LLMProvider:
    name: str

    def generate(self, prompt: str, model: str) -> LLMResponse:  # pragma: no cover - interface
        raise NotImplementedError

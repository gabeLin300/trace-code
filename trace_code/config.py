from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMSettings:
    default: str = "ollama:qwen3:8b-instruct"
    ollama_fallback: str = "ollama:qwen3:14b-instruct"
    fallback: str = "groq:openai/gpt-oss-20b"
    openai_enabled: bool = False


@dataclass
class MCPSettings:
    mode: str = "hybrid"


@dataclass
class UISettings:
    show_banner: bool = True


@dataclass
class SafetySettings:
    confirm_non_read: bool = True
    read_only: bool = False


@dataclass
class RetrySettings:
    max_attempts: int = 3
    base_delays: tuple[float, ...] = (1.0, 2.0, 4.0)
    jitter_ratio: float = 0.25
    max_single_wait: float = 8.0
    max_total_wait: float = 10.0


@dataclass
class TraceSettings:
    workspace_root: Path = field(default_factory=Path.cwd)
    llm: LLMSettings = field(default_factory=LLMSettings)
    mcp: MCPSettings = field(default_factory=MCPSettings)
    ui: UISettings = field(default_factory=UISettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    retry: RetrySettings = field(default_factory=RetrySettings)

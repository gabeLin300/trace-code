from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import shutil
import sys


@dataclass
class LLMSettings:
    default: str = "groq:openai/gpt-oss-120b"
    ollama_fallback: str = "ollama:qwen3:14b-instruct"
    fallback: str = "groq:llama-3.1-8b-instant"
    openai_enabled: bool = False


@dataclass
class MCPSettings:
    mode: str = "managed"
    filesystem_server_command: str = "npx -y @modelcontextprotocol/server-filesystem"
    local_knowledge_server_command: str = "python -m trace_code.mcp.local_knowledge_server"
    web_search_server_command: str = "python -m trace_code.mcp.web_search_server --no-prompt"
    startup_timeout_s: float = 8.0
    tools_timeout_s: float = 3.0
    operation_timeout_s: float = 20.0
    ingest_timeout_s: float = 300.0

    def filesystem_server_argv(self) -> list[str]:
        argv = shlex.split(self.filesystem_server_command)
        if not argv:
            return argv
        first = argv[0].lower()
        if first in {"npx", "npx.cmd"}:
            resolved = _resolve_npx_executable()
            if resolved:
                argv[0] = resolved
        return argv

    def local_knowledge_server_argv(self) -> list[str]:
        return _resolve_python_argv(shlex.split(self.local_knowledge_server_command))

    def web_search_server_argv(self) -> list[str]:
        return _resolve_python_argv(shlex.split(self.web_search_server_command))


@dataclass
class UISettings:
    show_banner: bool = True
    stream_responses: bool = True


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
class RagSettings:
    langchain_docs_seed_url: str = "https://python.langchain.com/docs/introduction/"
    langchain_docs_collection: str = "langchain_docs"
    top_k: int = 4


@dataclass
class WebSearchSettings:
    enabled: bool = True
    api_key_env_var: str = "TAVILY_API_KEY"
    default_max_results: int = 5
    default_search_depth: str = "basic"
    web_context_max_chars: int = 2000


@dataclass
class TraceSettings:
    workspace_root: Path = field(default_factory=Path.cwd)
    llm: LLMSettings = field(default_factory=LLMSettings)
    mcp: MCPSettings = field(default_factory=MCPSettings)
    ui: UISettings = field(default_factory=UISettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    retry: RetrySettings = field(default_factory=RetrySettings)
    rag: RagSettings = field(default_factory=RagSettings)
    web_search: WebSearchSettings = field(default_factory=WebSearchSettings)
    fast_path_enabled: bool = True


def _resolve_python_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    first = argv[0].lower()
    if first in {"python", "python3", "py"}:
        argv = [sys.executable, *argv[1:]]
    return argv


def _resolve_npx_executable() -> str | None:
    candidates = []
    if os.name == "nt":
        candidates.extend(["npx.cmd", "npx.exe", "npx"])
    else:
        candidates.append("npx")

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None

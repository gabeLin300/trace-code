from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shlex


@dataclass
class LLMSettings:
    default: str = "groq:llama-3.3-70b-versatile"
    ollama_fallback: str = "ollama:qwen3:14b-instruct"
    fallback: str = "groq:llama-3.1-8b-instant"
    openai_enabled: bool = False


@dataclass
class MCPSettings:
    mode: str = "managed"
    filesystem_server_command: str = "npx -y @modelcontextprotocol/server-filesystem"
    local_knowledge_server_command: str = "python -m trace_code.mcp.local_knowledge_server"
    web_search_server_command: str = "python -m trace_code.mcp.web_search_server"

    def filesystem_server_argv(self) -> list[str]:
        return shlex.split(self.filesystem_server_command)

    def local_knowledge_server_argv(self) -> list[str]:
        return shlex.split(self.local_knowledge_server_command)

    def web_search_server_argv(self) -> list[str]:
        return shlex.split(self.web_search_server_command)


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

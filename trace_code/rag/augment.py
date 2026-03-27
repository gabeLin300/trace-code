from __future__ import annotations

from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.knowledge.langchain_docs import search_langchain_docs
from trace_code.mcp.manager import MCPManager
from trace_code.mcp.web_search_server import resolve_tavily_api_key, tavily_search


def build_augmented_prompt(
    user_input: str,
    *,
    settings: TraceSettings,
    workspace_root: Path,
    mcp_manager: MCPManager | None = None,
) -> str:
    """Build a model prompt augmented with retrieved context when available."""
    local_context = _retrieve_local_knowledge_context(
        query=user_input,
        settings=settings,
        workspace_root=workspace_root,
        mcp_manager=mcp_manager,
    )
    web_context = _maybe_retrieve_web_context(
        query=user_input,
        settings=settings,
        mcp_manager=mcp_manager,
    )

    sections: list[str] = []
    if local_context:
        sections.append("## Local Knowledge Context\n" + local_context)
    if web_context:
        sections.append("## Web Search Context\n" + web_context)

    if not sections:
        return user_input

    return (
        "Use the context below when it is relevant and factual. "
        "If context is insufficient or conflicting, say so briefly.\n\n"
        + "\n\n".join(sections)
        + "\n\n"
        + "## User Question\n"
        + user_input
    )


def _retrieve_local_knowledge_context(
    *,
    query: str,
    settings: TraceSettings,
    workspace_root: Path,
    mcp_manager: MCPManager | None,
) -> str:
    if not should_use_local_knowledge(query):
        return ""

    try:
        if mcp_manager is not None:
            result = mcp_manager.search_langchain_docs(
                query=query,
                top_k=settings.rag.top_k,
                collection=settings.rag.langchain_docs_collection,
            )
        else:
            result = search_langchain_docs(
                query=query,
                persist_dir=_knowledge_persist_dir(workspace_root),
                collection_name=settings.rag.langchain_docs_collection,
                top_k=settings.rag.top_k,
            )
    except Exception:
        return ""

    items = result.get("results", [])
    if not items:
        return ""

    lines: list[str] = []
    for idx, item in enumerate(items[: settings.rag.top_k], start=1):
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {}) or {}
        source_url = metadata.get("source_url", "unknown")
        text = " ".join(str(item.get("text", "")).split())[:350]
        if text:
            lines.append(f"{idx}. {source_url}\n{text}")
    return "\n\n".join(lines)


def should_use_local_knowledge(query: str) -> bool:
    lowered = query.lower()
    signals = (
        "langchain",
        "rag",
        "retriever",
        "vector db",
        "chroma",
        "mcp",
        "documentation",
        "docs",
    )
    return any(sig in lowered for sig in signals)


def _maybe_retrieve_web_context(
    *,
    query: str,
    settings: TraceSettings,
    mcp_manager: MCPManager | None,
) -> str:
    if not settings.web_search.enabled:
        return ""
    if not should_use_web_search(query):
        return ""

    try:
        if mcp_manager is not None:
            result = mcp_manager.web_search(
                query=query,
                max_results=settings.web_search.default_max_results,
                search_depth=settings.web_search.default_search_depth,
            )
        else:
            api_key = resolve_tavily_api_key(
                explicit_api_key=None,
                env_var_name=settings.web_search.api_key_env_var,
                prompt_if_missing=False,
            )
            result = tavily_search(
                api_key=api_key,
                query=query,
                max_results=settings.web_search.default_max_results,
                search_depth=settings.web_search.default_search_depth,
            )
    except Exception:
        return ""

    results = result.get("results", [])
    answer = str(result.get("answer", "")).strip()

    lines: list[str] = []
    if answer:
        lines.append(f"Summary: {answer}")

    for idx, item in enumerate(results[: settings.web_search.default_max_results], start=1):
        if not isinstance(item, dict):
            continue
        title = item.get("title", "Untitled")
        url = item.get("url", "unknown")
        content = " ".join(str(item.get("content", "")).split())[:280]
        lines.append(f"{idx}. {title} ({url})\n{content}")

    return "\n\n".join(lines)


def should_use_web_search(query: str) -> bool:
    lowered = query.lower()
    recency_signals = (
        "latest",
        "recent",
        "today",
        "new",
        "current",
        "news",
        "release",
        "version",
    )
    return any(sig in lowered for sig in recency_signals)


def _knowledge_persist_dir(workspace_root: Path) -> Path:
    return workspace_root / ".assistant" / "vector_db" / "langchain_docs"

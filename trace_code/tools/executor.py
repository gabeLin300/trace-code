from __future__ import annotations

from pathlib import Path
import re
import subprocess

from trace_code.config import TraceSettings
from trace_code.knowledge.langchain_docs import index_langchain_docs, search_langchain_docs
from trace_code.mcp.filesystem_client import FilesystemMCPClient, MCPClientError
from trace_code.mcp.manager import MCPManager
from trace_code.mcp.web_search_client import WebSearchMCPClient, WebSearchMCPClientError
from trace_code.mcp.web_search_server import TavilyError, resolve_tavily_api_key, tavily_search
from trace_code.safety.classifier import classify_command


class ToolExecutionError(RuntimeError):
    pass


def prompt_requests_tool(user_input: str) -> bool:
    lowered = user_input.strip().lower()
    return (
        "list files" in lowered
        or lowered.startswith("read file ")
        or "ingest langchain docs" in lowered
        or "index langchain docs" in lowered
        or "search langchain docs" in lowered
        or "query langchain docs" in lowered
        or "find in langchain docs" in lowered
        or "search web" in lowered
        or "web search" in lowered
        or lowered.startswith("find on web ")
        or lowered.startswith("find online ")
        or lowered.startswith("run command ")
        or lowered.startswith("execute command ")
        or lowered.startswith("shell ")
        or lowered.startswith("confirm run command ")
        or lowered.startswith("confirm execute command ")
        or lowered.startswith("confirm shell ")
    )


def execute_tool_from_prompt(
    user_input: str,
    workspace_root: Path,
    settings: TraceSettings | None = None,
    mcp_manager: MCPManager | None = None,
) -> dict:
    settings = settings or TraceSettings(workspace_root=workspace_root)
    text = user_input.strip()
    lowered = text.lower()

    if "list files" in lowered:
        return _list_files(workspace_root, settings, mcp_manager)

    if lowered.startswith("read file "):
        path_text = text[len("read file ") :].strip()
        if not path_text:
            raise ToolExecutionError("missing file path for read file")
        return _read_file(workspace_root, path_text, settings, mcp_manager)

    if "ingest langchain docs" in lowered or "index langchain docs" in lowered:
        return _ingest_langchain_docs(workspace_root, text, settings, mcp_manager)

    if (
        "search langchain docs" in lowered
        or "query langchain docs" in lowered
        or "find in langchain docs" in lowered
    ):
        return _search_langchain_docs(workspace_root, text, settings, mcp_manager)

    if "search web" in lowered or "web search" in lowered or lowered.startswith("find on web ") or lowered.startswith(
        "find online "
    ):
        return _search_web(text, settings, mcp_manager)

    shell_command, confirmed = _extract_shell_command(text)
    if shell_command:
        return _execute_shell_command(shell_command, confirmed, workspace_root, settings)

    raise ToolExecutionError("unsupported tool request")


def _list_files(workspace_root: Path, settings: TraceSettings, mcp_manager: MCPManager | None) -> dict:
    output = _list_files_via_mcp(workspace_root, settings, mcp_manager)
    return {
        "tool_name": "fs.list",
        "status": "ok",
        "output": output,
    }


def _read_file(workspace_root: Path, path_text: str, settings: TraceSettings, mcp_manager: MCPManager | None) -> dict:
    target = (workspace_root / path_text).resolve()
    workspace_resolved = workspace_root.resolve()

    if workspace_resolved not in target.parents and target != workspace_resolved:
        raise ToolExecutionError("path is outside workspace")
    content = _read_file_via_mcp(target, workspace_root, settings, mcp_manager)
    return {
        "tool_name": "fs.read",
        "status": "ok",
        "output": content,
    }


def _knowledge_persist_dir(workspace_root: Path) -> Path:
    return workspace_root / ".assistant" / "vector_db" / "langchain_docs"


def _ingest_langchain_docs(
    workspace_root: Path, text: str, settings: TraceSettings, mcp_manager: MCPManager | None
) -> dict:
    max_pages = 25
    match = re.search(r"max pages\s+(\d+)", text.lower())
    if match is not None:
        max_pages = max(1, int(match.group(1)))

    try:
        if mcp_manager is not None:
            result = mcp_manager.ingest_langchain_docs(
                seed_url=settings.rag.langchain_docs_seed_url,
                max_pages=max_pages,
                collection=settings.rag.langchain_docs_collection,
            )
        else:
            result = index_langchain_docs(
                seed_url=settings.rag.langchain_docs_seed_url,
                persist_dir=_knowledge_persist_dir(workspace_root),
                collection_name=settings.rag.langchain_docs_collection,
                max_pages=max_pages,
            )
    except Exception as exc:
        raise ToolExecutionError(f"knowledge ingest failed: {exc}") from exc

    output = (
        f"Indexed LangChain docs.\n"
        f"seed_url={result['seed_url']}\n"
        f"pages_indexed={result['pages_indexed']}\n"
        f"chunks_indexed={result['chunks_indexed']}\n"
        f"collection={result['collection']}"
    )
    return {
        "tool_name": "knowledge.ingest_langchain_docs",
        "status": "ok",
        "output": output,
    }


def _search_langchain_docs(
    workspace_root: Path, text: str, settings: TraceSettings, mcp_manager: MCPManager | None
) -> dict:
    query = _extract_langchain_query(text)
    if not query:
        raise ToolExecutionError("missing query for LangChain docs search")

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
    except Exception as exc:
        raise ToolExecutionError(f"knowledge search failed: {exc}") from exc

    items = result["results"]
    if not items:
        output = "No indexed LangChain docs matched that query. Run ingest first if needed."
    else:
        lines = []
        for idx, item in enumerate(items, start=1):
            metadata = item.get("metadata", {})
            source_url = metadata.get("source_url", "unknown")
            snippet = " ".join(str(item.get("text", "")).split())
            preview = snippet[:280]
            lines.append(f"{idx}. {source_url}\n{preview}")
        output = "\n\n".join(lines)

    return {
        "tool_name": "knowledge.search_langchain_docs",
        "status": "ok",
        "output": output,
    }


def _extract_langchain_query(text: str) -> str:
    lowered = text.lower()
    for prefix in ("search langchain docs", "query langchain docs", "find in langchain docs"):
        if lowered.startswith(prefix):
            tail = text[len(prefix) :].strip()
            if tail.lower().startswith("for "):
                tail = tail[4:].strip()
            return tail
    marker = "langchain docs"
    if marker in lowered:
        idx = lowered.find(marker) + len(marker)
        tail = text[idx:].strip()
        if tail.lower().startswith("for "):
            tail = tail[4:].strip()
        return tail
    return ""


def _search_web(text: str, settings: TraceSettings, mcp_manager: MCPManager | None) -> dict:
    query = _extract_web_query(text)
    if not query:
        raise ToolExecutionError("missing query for web search")

    try:
        result = _web_search_via_mcp(query=query, settings=settings, mcp_manager=mcp_manager)
    except WebSearchMCPClientError:
        # Fallback keeps the agent usable when MCP web server is not running but API key is available.
        try:
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
        except TavilyError as exc:
            raise ToolExecutionError(f"web search failed: {exc}") from exc

    output = _format_web_search_output(result)
    return {
        "tool_name": "web.search",
        "status": "ok",
        "output": output,
    }


def _extract_web_query(text: str) -> str:
    lowered = text.lower().strip()
    prefixes = (
        "search web for ",
        "search the web for ",
        "web search for ",
        "find on web ",
        "find online ",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return text[len(prefix) :].strip()

    for marker in ("search web", "web search"):
        if marker in lowered:
            idx = lowered.find(marker) + len(marker)
            tail = text[idx:].strip()
            if tail.lower().startswith("for "):
                tail = tail[4:].strip()
            return tail
    return ""


def _web_search_via_mcp(query: str, settings: TraceSettings, mcp_manager: MCPManager | None = None) -> dict:
    if mcp_manager is not None:
        return mcp_manager.web_search(
            query=query,
            max_results=settings.web_search.default_max_results,
            search_depth=settings.web_search.default_search_depth,
        )
    with WebSearchMCPClient(command=settings.mcp.web_search_server_argv()) as client:
        return client.search(
            query=query,
            max_results=settings.web_search.default_max_results,
            search_depth=settings.web_search.default_search_depth,
        )


def _format_web_search_output(result: dict) -> str:
    answer = str(result.get("answer", "")).strip()
    results = result.get("results") or []

    lines: list[str] = []
    if answer:
        lines.append(f"Answer: {answer}")

    if not results:
        lines.append("No web results returned.")
        return "\n".join(lines)

    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        title = item.get("title", "") or "Untitled"
        url = item.get("url", "") or "unknown-url"
        content = " ".join(str(item.get("content", "")).split())
        preview = content[:220]
        lines.append(f"{idx}. {title}\n{url}\n{preview}")

    return "\n\n".join(lines)


def _extract_shell_command(text: str) -> tuple[str, bool]:
    lowered = text.lower().strip()
    confirmed = False
    if lowered.startswith("confirm "):
        confirmed = True
        text = text[len("confirm ") :].strip()
        lowered = text.lower()

    prefixes = ("run command ", "execute command ", "shell ")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            command = text[len(prefix) :].strip()
            return command, confirmed
    return "", False


def _execute_shell_command(command: str, confirmed: bool, workspace_root: Path, settings: TraceSettings) -> dict:
    classification = classify_command(command)

    if classification == "blocked":
        return {
            "tool_name": "shell.exec",
            "status": "blocked",
            "output": "Blocked by safety policy: command matches a dangerous pattern.",
        }

    if settings.safety.read_only and classification != "read":
        return {
            "tool_name": "shell.exec",
            "status": "blocked",
            "output": "Blocked by safety policy: read-only mode is enabled.",
        }

    if classification == "non_read" and settings.safety.confirm_non_read and not confirmed:
        return {
            "tool_name": "shell.exec",
            "status": "requires_confirmation",
            "output": (
                "This command is non-read and requires confirmation. "
                f"Retry with: confirm run command {command}"
            ),
        }

    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(workspace_root),
        text=True,
        capture_output=True,
    )
    output = completed.stdout.strip()
    error = completed.stderr.strip()

    if completed.returncode != 0:
        stderr_text = error or "shell command failed"
        raise ToolExecutionError(stderr_text)

    return {
        "tool_name": "shell.exec",
        "status": "ok",
        "output": output,
    }


def _list_files_via_mcp(workspace_root: Path, settings: TraceSettings, mcp_manager: MCPManager | None) -> str:
    if mcp_manager is not None:
        try:
            return mcp_manager.list_files(workspace_root)
        except Exception:
            pass
    try:
        with FilesystemMCPClient(
            command=settings.mcp.filesystem_server_argv(),
            workspace_root=workspace_root,
        ) as client:
            return client.list_directory(workspace_root)
    except MCPClientError:
        entries = sorted(p.name for p in workspace_root.iterdir())
        return "\n".join(entries)


def _read_file_via_mcp(
    target_path: Path, workspace_root: Path, settings: TraceSettings, mcp_manager: MCPManager | None
) -> str:
    if mcp_manager is not None:
        try:
            return mcp_manager.read_file(target_path)
        except Exception:
            pass
    try:
        with FilesystemMCPClient(
            command=settings.mcp.filesystem_server_argv(),
            workspace_root=workspace_root,
        ) as client:
            return client.read_file(target_path)
    except MCPClientError:
        if not target_path.exists() or not target_path.is_file():
            raise ToolExecutionError("file does not exist")
        return target_path.read_text(encoding="utf-8")

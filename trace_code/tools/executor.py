from __future__ import annotations

import json
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


TOOL_ALIASES = {
    "web_search": "web.search",
    "websearch": "web.search",
    "filesystem_read": "fs.read",
    "filesystem_write": "fs.write",
    "filesystem_list": "fs.list",
    "filesystem_search": "fs.search_code",
    "read_file": "fs.read",
    "write_file": "fs.write",
    "list_directory": "fs.list",
    "search_code": "fs.search_code",
    "shell": "shell.exec",
    "mcp_call": "mcp.call",
}


def supported_tool_specs() -> list[dict]:
    return [
        {"name": "fs.list", "arguments": {"path": "optional relative path"}, "description": "List files in a directory"},
        {"name": "fs.read", "arguments": {"path": "relative file path"}, "description": "Read file contents"},
        {
            "name": "fs.search_code",
            "arguments": {"query": "text or regex", "path": "optional relative dir", "max_results": "optional int"},
            "description": "Search code/text in workspace",
        },
        {"name": "fs.write", "arguments": {"path": "relative file path", "content": "text"}, "description": "Write file content"},
        {
            "name": "fs.edit",
            "arguments": {"path": "relative file path", "find": "old text", "replace": "new text"},
            "description": "Find/replace in a file",
        },
        {
            "name": "knowledge.ingest_langchain_docs",
            "arguments": {"max_pages": "optional int"},
            "description": "Ingest LangChain docs into local RAG store",
        },
        {
            "name": "knowledge.search_langchain_docs",
            "arguments": {"query": "search query"},
            "description": "Search local RAG LangChain docs index",
        },
        {
            "name": "web.search",
            "arguments": {"query": "web query", "max_results": "optional int"},
            "description": "Search the web using external MCP server",
        },
        {
            "name": "shell.exec",
            "arguments": {"command": "shell command", "confirmed": "optional bool"},
            "description": "Run shell command with safety policies",
        },
        {
            "name": "mcp.call",
            "arguments": {
                "server": "filesystem|local_knowledge|web_search",
                "tool": "dynamic MCP tool name",
                "arguments": "JSON object of tool arguments",
            },
            "description": "Invoke a dynamically discovered tool from an MCP server",
        },
    ]


def prompt_requests_tool(user_input: str) -> bool:
    lowered = user_input.strip().lower()
    return (
        "list files" in lowered
        or lowered.startswith("read file ")
        or lowered.startswith("read ")
        or lowered.startswith("write file ")
        or lowered.startswith("edit file ")
        or lowered.startswith("search code for ")
        or lowered.startswith("grep ")
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


def execute_tool_call(
    *,
    tool_name: str,
    arguments: dict,
    workspace_root: Path,
    settings: TraceSettings | None = None,
    mcp_manager: MCPManager | None = None,
) -> dict:
    settings = settings or TraceSettings(workspace_root=workspace_root)
    tool = normalize_tool_name(tool_name)
    args = arguments or {}

    if tool == "fs.list":
        path_text = str(args.get("path", "")).strip()
        target = workspace_root if not path_text else _resolve_workspace_path(workspace_root, path_text)
        out = _list_files_via_mcp(target, settings, mcp_manager)
        return {"tool_name": "fs.list", "status": "ok", "output": out, "arguments": {"path": str(target)}}

    if tool == "fs.read":
        path_text = str(args.get("path", "")).strip()
        if not path_text:
            raise ToolExecutionError("missing argument: path")
        target = _resolve_workspace_path(workspace_root, path_text)
        out = _read_file_via_mcp(target, workspace_root, settings, mcp_manager)
        return {"tool_name": "fs.read", "status": "ok", "output": out, "arguments": {"path": path_text}}

    if tool == "fs.search_code":
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolExecutionError("missing argument: query")
        path_text = str(args.get("path", "")).strip()
        root = workspace_root if not path_text else _resolve_workspace_path(workspace_root, path_text)
        max_results = int(args.get("max_results", 25) or 25)
        out = _search_code(root=root, query=query, max_results=max_results)
        return {
            "tool_name": "fs.search_code",
            "status": "ok",
            "output": out,
            "arguments": {"query": query, "path": str(root), "max_results": max_results},
        }

    if tool == "fs.write":
        path_text = str(args.get("path", "")).strip()
        content = str(args.get("content", ""))
        if not path_text:
            raise ToolExecutionError("missing argument: path")
        target = _resolve_workspace_path(workspace_root, path_text)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "tool_name": "fs.write",
            "status": "ok",
            "output": f"Wrote {len(content)} bytes to {path_text}",
            "arguments": {"path": path_text},
        }

    if tool == "fs.edit":
        path_text = str(args.get("path", "")).strip()
        find = str(args.get("find", ""))
        replace = str(args.get("replace", ""))
        if not path_text or not find:
            raise ToolExecutionError("missing arguments: path/find")
        target = _resolve_workspace_path(workspace_root, path_text)
        if not target.exists() or not target.is_file():
            raise ToolExecutionError("file does not exist")
        original = target.read_text(encoding="utf-8")
        if find not in original:
            raise ToolExecutionError("edit target not found")
        updated = original.replace(find, replace)
        target.write_text(updated, encoding="utf-8")
        return {
            "tool_name": "fs.edit",
            "status": "ok",
            "output": f"Updated {path_text}: replaced {original.count(find)} occurrence(s).",
            "arguments": {"path": path_text},
        }

    if tool == "knowledge.ingest_langchain_docs":
        max_pages = int(args.get("max_pages", 25) or 25)
        return _ingest_langchain_docs(workspace_root, f"ingest langchain docs max pages {max_pages}", settings, mcp_manager)

    if tool == "knowledge.search_langchain_docs":
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolExecutionError("missing argument: query")
        return _search_langchain_docs(workspace_root, f"search langchain docs for {query}", settings, mcp_manager)

    if tool == "web.search":
        query = str(args.get("query", "")).strip()
        if not query:
            raise ToolExecutionError("missing argument: query")
        return _search_web(f"search web for {query}", settings, mcp_manager)

    if tool == "shell.exec":
        command = str(args.get("command", "")).strip()
        if not command:
            raise ToolExecutionError("missing argument: command")
        confirmed = bool(args.get("confirmed", False))
        result = _execute_shell_command(command, confirmed, workspace_root, settings)
        result["arguments"] = {"command": command, "confirmed": confirmed}
        return result

    if tool == "mcp.call":
        server = str(args.get("server", "")).strip()
        mcp_tool = str(args.get("tool", "")).strip()
        mcp_args = args.get("arguments", {})
        if not server:
            raise ToolExecutionError("missing argument: server")
        if not mcp_tool:
            raise ToolExecutionError("missing argument: tool")
        if not isinstance(mcp_args, dict):
            raise ToolExecutionError("argument 'arguments' must be an object")
        if mcp_manager is None:
            raise ToolExecutionError("mcp.call requires an active MCP manager")
        try:
            raw = mcp_manager.invoke_tool(server=server, tool=mcp_tool, arguments=mcp_args)
        except Exception as exc:
            raise ToolExecutionError(f"dynamic MCP call failed: {exc}") from exc
        output = _format_generic_mcp_result(raw)
        return {
            "tool_name": "mcp.call",
            "status": "ok",
            "output": output,
            "arguments": {"server": server, "tool": mcp_tool, "arguments": mcp_args},
        }

    raise ToolExecutionError(f"unsupported tool name: {tool_name}")


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

    if lowered.startswith("read "):
        path_text = text[len("read ") :].strip()
        if not path_text or path_text in {"file", "files"}:
            raise ToolExecutionError("missing file path for read")
        return _read_file(workspace_root, path_text, settings, mcp_manager)

    if lowered.startswith("write file "):
        rest = text[len("write file ") :].strip()
        path_text, sep, content = rest.partition(" with content ")
        if not path_text or not sep:
            raise ToolExecutionError("write file format: write file <path> with content <text>")
        return execute_tool_call(
            tool_name="fs.write",
            arguments={"path": path_text.strip(), "content": content},
            workspace_root=workspace_root,
            settings=settings,
            mcp_manager=mcp_manager,
        )

    if lowered.startswith("edit file "):
        # format: edit file <path> replace <old> with <new>
        rest = text[len("edit file ") :].strip()
        parts = re.split(r"\s+replace\s+", rest, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            raise ToolExecutionError("edit file format: edit file <path> replace <old> with <new>")
        path_text = parts[0].strip()
        tail = parts[1]
        idx = re.search(r"\s+with\s+", tail, flags=re.IGNORECASE)
        if idx is None:
            raise ToolExecutionError("edit file format: edit file <path> replace <old> with <new>")
        split_at = idx.start()
        find_text = tail[:split_at].strip()
        replace_text = tail[idx.end() :].strip()
        return execute_tool_call(
            tool_name="fs.edit",
            arguments={"path": path_text, "find": find_text, "replace": replace_text},
            workspace_root=workspace_root,
            settings=settings,
            mcp_manager=mcp_manager,
        )

    if lowered.startswith("search code for ") or lowered.startswith("grep "):
        query = text.split(" ", 3)[-1].strip() if lowered.startswith("grep ") else text[len("search code for ") :].strip()
        return execute_tool_call(
            tool_name="fs.search_code",
            arguments={"query": query},
            workspace_root=workspace_root,
            settings=settings,
            mcp_manager=mcp_manager,
        )

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
    target = _resolve_workspace_path(workspace_root, path_text)
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
        # Always call in-process — avoids MCP subprocess startup + IPC overhead.
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
        "arguments": {"query": query},
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


def _format_generic_mcp_result(result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)
    structured = result.get("structuredContent")
    if structured is not None:
        return json.dumps(structured, ensure_ascii=True, indent=2)
    content = result.get("content")
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    texts.append(text)
        if texts:
            return "\n".join(texts)
    return json.dumps(result, ensure_ascii=True, indent=2)


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
            "confirmation_required": True,
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
        "confirmation_required": False,
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


def _resolve_workspace_path(workspace_root: Path, path_text: str) -> Path:
    target = (workspace_root / path_text).resolve()
    workspace_resolved = workspace_root.resolve()
    if workspace_resolved not in target.parents and target != workspace_resolved:
        raise ToolExecutionError("path is outside workspace")
    return target


def _search_code(root: Path, query: str, max_results: int = 25) -> str:
    max_results = max(1, min(max_results, 200))
    try:
        completed = subprocess.run(
            ["rg", "-n", "-S", query, str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode in {0, 1}:  # 1 means no matches
            lines = [line for line in completed.stdout.splitlines() if line.strip()]
            return "\n".join(lines[:max_results]) if lines else "No matches found."
    except Exception:
        pass

    # Fallback without ripgrep.
    hits: list[str] = []
    for path in root.rglob("*"):
        if len(hits) >= max_results:
            break
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            if query.lower() in line.lower():
                rel = path.relative_to(root)
                hits.append(f"{rel}:{idx}:{line.strip()}")
                if len(hits) >= max_results:
                    break
    return "\n".join(hits) if hits else "No matches found."


def normalize_tool_name(tool_name: str) -> str:
    raw = (tool_name or "").strip()
    lowered = raw.lower()
    return TOOL_ALIASES.get(lowered, raw)

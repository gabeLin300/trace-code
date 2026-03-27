from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable

from trace_code.agent.loop import run_agentic_task
from trace_code.cli.banner import render_banner
from trace_code.cli.router import route_user_input
from trace_code.config import TraceSettings
from trace_code.llm.base import ProviderError, ProviderSelectionError
from trace_code.llm.manager import LLMManager
from trace_code.llm.manager import parse_provider_route
from trace_code.mcp.manager import MCPManager
from trace_code.rag.augment import build_augmented_prompt
from trace_code.sessions.store import SessionRecord, SessionStore
from trace_code.tools.executor import prompt_requests_tool
from trace_code.tools.executor import supported_tool_specs
from trace_code.utils.timeout import call_with_timeout
from trace_code.workspace.bootstrap import bootstrap_workspace

# Debug toggle for local demos:
# Set to False (or uncomment below) to hide [debug] lines.
CLI_DEBUG = False
# CLI_DEBUG = False


@dataclass
class CLIContext:
    settings: TraceSettings
    store: SessionStore
    session: SessionRecord
    resumed: bool
    banner: str
    sessions_dir: str
    mcp_manager: MCPManager | None


HELP_TEXT = (
    "Commands:\n"
    "  /help      Show command usage\n"
    "  /config    Show active configuration summary\n"
    "  /sessions  Show current session details\n"
    "  /health    Run provider/auth diagnostics\n"
    "  /tools     Show typed + dynamic MCP tool inventory\n"
    "  /exit      Exit the CLI"
)


def _init_context(settings: TraceSettings, no_banner: bool, session_id: str, start_mcp: bool = False) -> CLIContext:
    dirs = bootstrap_workspace(Path(settings.workspace_root))
    banner = render_banner(show_banner=settings.ui.show_banner and not no_banner)
    store = SessionStore(dirs["sessions"])
    path = store.path_for(session_id)
    if path.exists():
        session = store.load(session_id)
        resumed = True
    else:
        session = SessionRecord(session_id=session_id)
        store.save(session)
        resumed = False

    mcp_manager: MCPManager | None = None
    if start_mcp:
        mcp_manager = MCPManager(settings=settings, workspace_root=Path(settings.workspace_root))

    return CLIContext(
        settings=settings,
        store=store,
        session=session,
        resumed=resumed,
        banner=banner,
        sessions_dir=str(dirs["sessions"]),
        mcp_manager=mcp_manager,
    )


def _summarize_config(settings: TraceSettings) -> str:
    execution_mode = "confirm" if settings.safety.confirm_non_read else "auto_execute"
    return (
        f"provider.default={settings.llm.default}\n"
        f"provider.fallback={settings.llm.fallback}\n"
        f"openai.enabled={settings.llm.openai_enabled}\n"
        f"mcp.mode={settings.mcp.mode}\n"
        f"ui.show_banner={settings.ui.show_banner}\n"
        f"ui.stream_responses={settings.ui.stream_responses}\n"
        f"safety.execution_mode={execution_mode}\n"
        f"safety.confirm_non_read={settings.safety.confirm_non_read}\n"
        f"safety.read_only={settings.safety.read_only}"
    )


def _sessions_text(ctx: CLIContext) -> str:
    state = "resumed" if ctx.resumed else "new"
    return f"session_id={ctx.session.session_id} ({state})\nsessions_dir={ctx.sessions_dir}"


def _startup_header_text(settings: TraceSettings) -> str:
    route = parse_provider_route(settings.llm.default)
    execution_mode = "confirm" if settings.safety.confirm_non_read else "auto_execute"
    return (
        f"workspace: {Path(settings.workspace_root).resolve()}\n"
        f"provider: {route.provider}\n"
        f"model: {route.model}\n"
        f"execution_mode: {execution_mode}\n"
        f"stream_responses: {settings.ui.stream_responses}"
    )


def _available_session_ids(ctx: CLIContext) -> list[str]:
    session_files = sorted(Path(ctx.sessions_dir).glob("*.json"))
    return [p.stem for p in session_files]


def _prompt_session_selection(ctx: CLIContext, input_fn: Callable[[], str], output_fn: Callable[[str], None]) -> str | None:
    session_ids = _available_session_ids(ctx)
    if not session_ids or (len(session_ids) == 1 and session_ids[0] == ctx.session.session_id and not ctx.resumed):
        return None

    output_fn(
        "Existing sessions found. "
        f"Current session is '{ctx.session.session_id}'. Type 'r' to resume or 'n' to create new."
    )
    while True:
        raw = input_fn().strip()
        choice = raw.lower()
        if choice in {"r", "resume"}:
            return None
        if choice in {"n", "new"}:
            output_fn("Enter new session id:")
            new_id = input_fn().strip()
            if not new_id:
                output_fn("Session id cannot be empty.")
                continue
            path = ctx.store.path_for(new_id)
            if path.exists():
                ctx.session = ctx.store.load(new_id)
                ctx.resumed = True
            else:
                ctx.session = SessionRecord(session_id=new_id)
                ctx.store.save(ctx.session)
                ctx.resumed = False
            return None
        # UX: if the user immediately types a normal command, keep default resume and process it.
        if raw and not raw.startswith(("/help", "/config", "/sessions", "/health", "/tools", "/exit")):
            output_fn("Using current session and continuing with your command.")
            return raw
        output_fn("Please enter 'r' or 'n'.")


def _handle_builtin(command: str, ctx: CLIContext) -> tuple[str, bool]:
    if command == "/help":
        return HELP_TEXT, False
    if command == "/config":
        return _summarize_config(ctx.settings), False
    if command == "/sessions":
        return _sessions_text(ctx), False
    if command == "/health":
        return _provider_health_text(ctx), False
    if command == "/tools":
        return _tools_text(ctx), False
    if command == "/exit":
        return "Exiting trace.", True
    return f"Unknown command: {command}", False


def _tools_text(ctx: CLIContext) -> str:
    typed = [spec["name"] for spec in supported_tool_specs()]
    lines = [
        "typed_tools=" + ", ".join(typed),
    ]
    if ctx.mcp_manager is None:
        lines.append("dynamic_mcp_tools=(mcp manager not started)")
        return "\n".join(lines)
    dynamic = ctx.mcp_manager.available_tools()
    for server_name in ("filesystem", "local_knowledge", "web_search"):
        tools = dynamic.get(server_name, [])
        lines.append(f"dynamic.{server_name}={tools}")
    return "\n".join(lines)


def _mask_key(raw: str) -> str:
    key = raw.strip()
    if not key:
        return "(missing)"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]} (len={len(key)})"


def _provider_health_text(ctx: CLIContext) -> str:
    settings = ctx.settings
    manager = LLMManager(settings)
    default_route = settings.llm.default
    fallback_route = settings.llm.fallback

    groq_key = _mask_key(os.getenv("GROQ_API_KEY", ""))
    tavily_key = _mask_key(os.getenv(settings.web_search.api_key_env_var, ""))

    lines = [
        "[debug] health start",
        f"GROQ_API_KEY={groq_key}",
        f"{settings.web_search.api_key_env_var}={tavily_key}",
        f"default_route={default_route}",
        f"fallback_route={fallback_route}",
    ]
    if ctx.mcp_manager is not None:
        lines.append("[debug] MCP diagnostics start")
        diag = ctx.mcp_manager.diagnostics()
        lines.append(
            "mcp_health="
            f"filesystem:{diag['filesystem'].connected},"
            f"local_knowledge:{diag['local_knowledge'].connected},"
            f"web_search:{diag['web_search'].connected}"
        )
        for server_name in ("filesystem", "local_knowledge", "web_search"):
            item = diag[server_name]
            lines.append(
                f"mcp.{server_name}: connected={item.connected} "
                f"tools={item.tools} executable={item.executable} detail={item.executable_detail} "
                f"category={item.failure_category}"
            )
            lines.append(
                f"mcp.{server_name}.launch_command={item.launch_command} "
                f"python={item.python_executable} venv={item.virtual_env or '(none)'}"
            )
            if item.startup_error:
                lines.append(f"mcp.{server_name}.startup_error={item.startup_error}")
                lines.append(f"mcp.{server_name}.remediation={item.remediation}")
        lines.append("[debug] MCP diagnostics end")

    for label, route in (("default", default_route), ("fallback", fallback_route)):
        lines.append(f"[debug] provider invocation start: {label}")
        try:
            ok, res, err = call_with_timeout(
                lambda: manager.generate("health check", provider_override=route),
                timeout_s=20.0,
            )
            if not ok:
                raise ProviderError(f"provider timeout/error: {err}")
            lines.append(f"{label}: ok ({res.provider}:{res.model})")
        except (ProviderError, ProviderSelectionError) as exc:
            lines.append(f"{label}: error ({route}) -> {exc}")
        lines.append(f"[debug] provider invocation end: {label}")

    lines.append("[debug] health end")

    return "\n".join(lines)


def start_cli(settings: TraceSettings, no_banner: bool = False, session_id: str = "default") -> dict:
    ctx = _init_context(settings, no_banner=no_banner, session_id=session_id, start_mcp=False)

    return {
        "banner": ctx.banner,
        "resumed": ctx.resumed,
        "session_id": ctx.session.session_id,
        "sessions_dir": ctx.sessions_dir,
    }


def run_interactive_session(
    settings: TraceSettings,
    input_fn: Callable[[], str],
    output_fn: Callable[[str], None],
    no_banner: bool = False,
    session_id: str = "default",
) -> SessionRecord:
    ctx = _init_context(settings, no_banner=no_banner, session_id=session_id, start_mcp=True)

    if ctx.banner:
        output_fn(ctx.banner)
    output_fn(_startup_header_text(ctx.settings))
    pending_user_input = _prompt_session_selection(ctx, input_fn, output_fn)

    try:
        while True:
            if pending_user_input is not None:
                user_input = pending_user_input.strip()
                pending_user_input = None
            else:
                user_input = input_fn().strip()
            if not user_input:
                continue
            _debug(output_fn, f"command received: {user_input}")

            ctx.session.command_history.append(user_input)
            route = route_user_input(user_input)
            _debug(output_fn, f"command routing: {route}")

            if route == "builtin":
                _debug(output_fn, "builtin handler start")
                text, should_exit = _handle_builtin(user_input, ctx)
                _debug(output_fn, "builtin handler end")
                output_fn(text)
                ctx.store.save(ctx.session)
                if should_exit:
                    break
                continue

            # True provider streaming path for non-tool prompts.
            if ctx.settings.ui.stream_responses and not prompt_requests_tool(user_input):
                stream_result = _stream_direct_llm_response(ctx, user_input, output_fn)
                ctx.session.chat_history.append({"role": "user", "content": user_input})
                ctx.session.chat_history.append({"role": "assistant", "content": stream_result})
                ctx.store.save(ctx.session)
                continue

            _debug(output_fn, "agent loop start")
            try:
                result = run_agentic_task(
                    user_input=user_input,
                    settings=ctx.settings,
                    mcp_manager=ctx.mcp_manager,
                    debug_fn=lambda msg: _debug(output_fn, msg),
                )
            except Exception as exc:
                _debug(output_fn, f"agent loop exception: {exc}")
                output_fn("[loop] stop_reason=error")
                output_fn(f"Agent loop failed: {exc}")
                continue
            _debug(output_fn, "agent loop end")
            response = result["response"]
            stop_reason = result.get("stop_reason")
            route = parse_provider_route(ctx.settings.llm.default)
            output_fn(f"[loop] provider={route.provider} model={route.model}")
            for tool_step in result.get("tools", []):
                tool_name = tool_step.get("tool_name")
                server = _tool_server_name(str(tool_name or ""))
                args = tool_step.get("arguments", {})
                required = bool(tool_step.get("confirmation_required", False))
                status = str(tool_step.get("status", "unknown"))
                elapsed_ms = int(tool_step.get("elapsed_ms", 0) or 0)
                summary = _summarize_tool_output(str(tool_step.get("output", "")))
                output_fn(f"[tool:{tool_step.get('step')}] status=planned tool={tool_name} server={server}")
                output_fn(f"[tool:{tool_step.get('step')}] status=running tool={tool_name} args={args}")
                output_fn(
                    f"[tool:{tool_step.get('step')}] status=finished tool={tool_name} "
                    f"result_status={status} elapsed_ms={elapsed_ms} confirmation_required={required}"
                )
                output_fn(f"[tool:{tool_step.get('step')}] result_or_blocked={summary}")
            if stop_reason:
                output_fn(f"[loop] stop_reason={stop_reason}")

            ctx.session.chat_history.append({"role": "user", "content": user_input})
            ctx.session.chat_history.append({"role": "assistant", "content": response})

            for tool_step in result.get("tools", []):
                ctx.session.tool_history.append(
                    {
                        "tool_name": tool_step.get("tool_name", "unknown"),
                        "status": tool_step.get("status", result.get("status", "unknown")),
                        "output": tool_step.get("output", ""),
                    }
                )
            if result.get("tool") and not result.get("tools"):
                ctx.session.tool_history.append(
                    {
                        "tool_name": result.get("tool", "unknown"),
                        "status": result.get("status", "unknown"),
                        "output": response,
                    }
                )

            ctx.store.save(ctx.session)
            _emit_response(output_fn, response, stream=ctx.settings.ui.stream_responses)
    finally:
        if ctx.mcp_manager is not None:
            ctx.mcp_manager.close()

    return ctx.session


def _summarize_tool_output(output: str, limit: int = 160) -> str:
    text = " ".join(output.split())
    if not text:
        return "(empty)"
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _debug(output_fn: Callable[[str], None], message: str) -> None:
    if CLI_DEBUG:
        output_fn(f"[debug] {message}")


def _tool_server_name(tool_name: str) -> str:
    normalized = tool_name.strip().lower()
    if normalized.startswith("fs."):
        return "filesystem"
    if normalized.startswith("knowledge."):
        return "local_knowledge"
    if normalized.startswith("web."):
        return "web_search"
    if normalized == "mcp.call":
        return "dynamic_mcp"
    if normalized.startswith("shell."):
        return "local_shell"
    return "unknown"


def _emit_response(output_fn: Callable[[str], None], response: str, *, stream: bool) -> None:
    if not stream:
        output_fn(response)
        return
    chunks = _stream_chunks(response)
    output_fn(f"[stream] chunks={len(chunks)}")
    for chunk in chunks:
        output_fn(chunk)


def _stream_chunks(text: str, chunk_size: int = 220) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return [""]
    words = normalized.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > chunk_size and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _stream_direct_llm_response(ctx: CLIContext, user_input: str, output_fn: Callable[[str], None]) -> str:
    manager = LLMManager(ctx.settings)
    prompt = build_augmented_prompt(
        user_input,
        settings=ctx.settings,
        workspace_root=Path(ctx.settings.workspace_root),
        mcp_manager=ctx.mcp_manager,
    )
    route = parse_provider_route(ctx.settings.llm.default)
    output_fn(f"[stream] provider={route.provider} model={route.model}")
    chunks: list[str] = []
    pending = ""
    try:
        for chunk in manager.generate_stream(prompt=prompt):
            if not chunk:
                continue
            chunks.append(chunk)
            pending += chunk
            ready_chunks, pending = _drain_stream_buffer(pending, max_chunk_chars=180)
            for ready in ready_chunks:
                output_fn(ready)
    except (ProviderError, ProviderSelectionError) as exc:
        msg = f"LLM error: {exc}"
        output_fn(msg)
        return msg
    if pending.strip():
        output_fn(pending.strip())
    text = "".join(chunks).strip()
    return text or "(empty response)"


def _drain_stream_buffer(buffer: str, *, max_chunk_chars: int) -> tuple[list[str], str]:
    """Return printable chunks from token deltas without 1-token-per-line noise."""
    out: list[str] = []
    pending = buffer

    while True:
        newline_idx = pending.find("\n")
        if newline_idx == -1:
            break
        ready = pending[:newline_idx].strip()
        pending = pending[newline_idx + 1 :]
        if ready:
            out.append(ready)

    while len(pending) >= max_chunk_chars:
        cut = pending.rfind(" ", 0, max_chunk_chars)
        if cut < 40:
            cut = max_chunk_chars
        ready = pending[:cut].strip()
        pending = pending[cut:].lstrip()
        if ready:
            out.append(ready)

    return out, pending

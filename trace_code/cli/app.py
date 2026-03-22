from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from trace_code.agent.loop import run_turn
from trace_code.cli.banner import render_banner
from trace_code.cli.router import route_user_input
from trace_code.config import TraceSettings
from trace_code.llm.manager import parse_provider_route
from trace_code.mcp.manager import MCPManager
from trace_code.sessions.store import SessionRecord, SessionStore
from trace_code.tools.executor import prompt_requests_tool
from trace_code.workspace.bootstrap import bootstrap_workspace


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
        mcp_manager.start()

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
    return (
        f"provider.default={settings.llm.default}\n"
        f"provider.fallback={settings.llm.fallback}\n"
        f"openai.enabled={settings.llm.openai_enabled}\n"
        f"mcp.mode={settings.mcp.mode}\n"
        f"ui.show_banner={settings.ui.show_banner}\n"
        f"safety.confirm_non_read={settings.safety.confirm_non_read}\n"
        f"safety.read_only={settings.safety.read_only}"
    )


def _sessions_text(ctx: CLIContext) -> str:
    state = "resumed" if ctx.resumed else "new"
    return f"session_id={ctx.session.session_id} ({state})\nsessions_dir={ctx.sessions_dir}"


def _guess_wants_tool(user_input: str) -> bool:
    return prompt_requests_tool(user_input)


def _startup_header_text(settings: TraceSettings) -> str:
    route = parse_provider_route(settings.llm.default)
    return (
        f"workspace: {Path(settings.workspace_root).resolve()}\n"
        f"provider: {route.provider}\n"
        f"model: {route.model}"
    )


def _available_session_ids(ctx: CLIContext) -> list[str]:
    session_files = sorted(Path(ctx.sessions_dir).glob("*.json"))
    return [p.stem for p in session_files]


def _prompt_session_selection(ctx: CLIContext, input_fn: Callable[[], str], output_fn: Callable[[str], None]) -> None:
    session_ids = _available_session_ids(ctx)
    if not session_ids or (len(session_ids) == 1 and session_ids[0] == ctx.session.session_id and not ctx.resumed):
        return

    output_fn(
        "Existing sessions found. "
        f"Current session is '{ctx.session.session_id}'. Type 'r' to resume or 'n' to create new."
    )
    while True:
        choice = input_fn().strip().lower()
        if choice in {"r", "resume"}:
            return
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
            return
        output_fn("Please enter 'r' or 'n'.")


def _handle_builtin(command: str, ctx: CLIContext) -> tuple[str, bool]:
    if command == "/help":
        return HELP_TEXT, False
    if command == "/config":
        return _summarize_config(ctx.settings), False
    if command == "/sessions":
        return _sessions_text(ctx), False
    if command == "/exit":
        return "Exiting trace.", True
    return f"Unknown command: {command}", False


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
    _prompt_session_selection(ctx, input_fn, output_fn)

    try:
        while True:
            user_input = input_fn().strip()
            if not user_input:
                continue

            ctx.session.command_history.append(user_input)
            route = route_user_input(user_input)

            if route == "builtin":
                text, should_exit = _handle_builtin(user_input, ctx)
                output_fn(text)
                ctx.store.save(ctx.session)
                if should_exit:
                    break
                continue

            wants_tool = _guess_wants_tool(user_input)
            result = run_turn(
                user_input=user_input,
                wants_tool=wants_tool,
                settings=ctx.settings,
                mcp_manager=ctx.mcp_manager,
            )
            if wants_tool:
                output_fn(f"\ncalling tool: {result['tool']}\n")
            response = result["response"]

            ctx.session.chat_history.append({"role": "user", "content": user_input})
            ctx.session.chat_history.append({"role": "assistant", "content": response})

            if result.get("tool"):
                ctx.session.tool_history.append(
                    {
                        "tool_name": result.get("tool", "unknown"),
                        "status": result["status"],
                        "output": response,
                    }
                )

            ctx.store.save(ctx.session)
            output_fn(response)
    finally:
        if ctx.mcp_manager is not None:
            ctx.mcp_manager.close()

    return ctx.session

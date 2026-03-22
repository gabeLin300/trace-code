from trace_code.cli.app import run_interactive_session
from trace_code.config import TraceSettings
from trace_code.sessions.store import SessionStore


def _make_input(values):
    it = iter(values)

    def _inner():
        return next(it)

    return _inner


def test_interactive_loop_handles_builtins_and_exit(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    outputs = []
    session = run_interactive_session(
        settings=settings,
        input_fn=_make_input(["/help", "/config", "/sessions", "/exit"]),
        output_fn=outputs.append,
        no_banner=True,
        session_id="s-help",
    )

    assert any("workspace:" in out for out in outputs)
    assert any("provider:" in out for out in outputs)
    assert any("model:" in out for out in outputs)
    assert any("Commands:" in out for out in outputs)
    assert any("provider.default" in out for out in outputs)
    assert any("session_id=s-help" in out for out in outputs)
    assert outputs[-1] == "Exiting trace."
    assert session.command_history == ["/help", "/config", "/sessions", "/exit"]


def test_interactive_loop_persists_agent_turns(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    outputs = []
    run_interactive_session(
        settings=settings,
        input_fn=_make_input(["list files in src", "/exit"]),
        output_fn=outputs.append,
        no_banner=True,
        session_id="s-agent",
    )

    store = SessionStore(tmp_path / ".assistant" / "sessions")
    saved = store.load("s-agent")

    assert any(out.strip() for out in outputs)
    assert saved.chat_history[0]["role"] == "user"
    assert saved.chat_history[1]["role"] == "assistant"
    assert saved.tool_history[0]["status"] == "tool_called"
    assert saved.tool_history[0]["tool_name"] == "fs.list"


def test_interactive_loop_persists_requires_confirmation_tool_status(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    outputs = []
    run_interactive_session(
        settings=settings,
        input_fn=_make_input(["run command touch demo.txt", "/exit"]),
        output_fn=outputs.append,
        no_banner=True,
        session_id="s-safety",
    )

    store = SessionStore(tmp_path / ".assistant" / "sessions")
    saved = store.load("s-safety")

    assert any("requires confirmation" in out.lower() for out in outputs)
    assert saved.tool_history[0]["status"] == "requires_confirmation"
    assert saved.tool_history[0]["tool_name"] == "shell.exec"


def test_interactive_loop_prompts_to_resume_or_create_when_session_exists(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    run_interactive_session(
        settings=settings,
        input_fn=_make_input(["/exit"]),
        output_fn=lambda _text: None,
        no_banner=True,
        session_id="existing",
    )

    outputs = []
    run_interactive_session(
        settings=settings,
        input_fn=_make_input(["n", "fresh-session", "/sessions", "/exit"]),
        output_fn=outputs.append,
        no_banner=True,
        session_id="existing",
    )

    assert any("Existing sessions found" in out for out in outputs)
    assert any("session_id=fresh-session" in out for out in outputs)

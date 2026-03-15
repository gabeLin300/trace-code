from trace_code.cli.app import start_cli
from trace_code.config import TraceSettings


def test_workspace_bootstrap_creates_assistant_dirs(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    start_cli(settings, session_id="s1")

    assert (tmp_path / ".assistant").exists()
    assert (tmp_path / ".assistant" / "sessions").exists()
    assert (tmp_path / ".assistant" / "logs").exists()
    assert (tmp_path / ".assistant" / "vector_db").exists()


def test_session_resume_flow(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    first = start_cli(settings, session_id="session-x")
    second = start_cli(settings, session_id="session-x")

    assert first["resumed"] is False
    assert second["resumed"] is True

from trace_code.cli import main as cli_main
from trace_code.cli.preflight import PreflightCheck, PreflightReport


def test_main_exits_cleanly(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["trace", "--no-banner", "--session-id", "main-test"])
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setattr(
        cli_main,
        "run_preflight",
        lambda settings, include_mcp_launchability=True: PreflightReport(checks=[PreflightCheck("x", True, "ok", "")]),
    )
    inputs = iter(["r", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    code = cli_main.main()

    captured = capsys.readouterr()
    assert code == 0
    assert "Exiting trace." in captured.out


def test_main_preflight_flag_exits_without_repl(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["trace", "--preflight"])
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setattr(
        cli_main,
        "run_preflight",
        lambda settings, include_mcp_launchability=True: PreflightReport(checks=[PreflightCheck("x", True, "ok", "")]),
    )

    code = cli_main.main()

    captured = capsys.readouterr()
    assert code == 0
    assert "Preflight result: PASS" in captured.out


def test_main_exits_nonzero_when_preflight_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["trace", "--no-banner"])
    monkeypatch.setattr(
        cli_main,
        "run_preflight",
        lambda settings, include_mcp_launchability=True: PreflightReport(checks=[PreflightCheck("x", False, "broken", "fix it")]),
    )

    code = cli_main.main()

    captured = capsys.readouterr()
    assert code == 2
    assert "Preflight result: FAIL" in captured.out


def test_main_applies_auto_exec_and_no_stream_flags(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["trace", "--auto-exec", "--no-stream"])
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setattr(
        cli_main,
        "run_preflight",
        lambda settings, include_mcp_launchability=True: PreflightReport(checks=[PreflightCheck("x", True, "ok", "")]),
    )

    captured = {}

    def _fake_run_interactive_session(settings, input_fn, output_fn, no_banner=False, session_id="default"):
        captured["confirm_non_read"] = settings.safety.confirm_non_read
        captured["stream_responses"] = settings.ui.stream_responses
        raise SystemExit(0)

    monkeypatch.setattr(cli_main, "run_interactive_session", _fake_run_interactive_session)

    try:
        cli_main.main()
    except SystemExit:
        pass

    assert captured["confirm_non_read"] is False
    assert captured["stream_responses"] is False

from trace_code.cli import main as cli_main
from trace_code.cli.preflight import PreflightCheck, PreflightReport


def test_main_exits_cleanly(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["trace", "--no-banner", "--session-id", "main-test"])
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setattr(
        cli_main,
        "run_preflight",
        lambda settings: PreflightReport(checks=[PreflightCheck("x", True, "ok", "")]),
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
        lambda settings: PreflightReport(checks=[PreflightCheck("x", True, "ok", "")]),
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
        lambda settings: PreflightReport(checks=[PreflightCheck("x", False, "broken", "fix it")]),
    )

    code = cli_main.main()

    captured = capsys.readouterr()
    assert code == 2
    assert "Preflight result: FAIL" in captured.out

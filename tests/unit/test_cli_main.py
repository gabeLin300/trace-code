from trace_code.cli import main as cli_main


def test_main_exits_cleanly(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["trace", "--no-banner", "--session-id", "main-test"])
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    inputs = iter(["r", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    code = cli_main.main()

    captured = capsys.readouterr()
    assert code == 0
    assert "Exiting trace." in captured.out

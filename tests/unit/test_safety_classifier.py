from trace_code.safety.classifier import classify_command


def test_classifies_read_commands() -> None:
    assert classify_command("rg foo") == "read"
    assert classify_command("git diff") == "read"


def test_classifies_non_read_commands() -> None:
    assert classify_command("pip install pytest") == "non_read"


def test_classifies_blocked_commands() -> None:
    assert classify_command("rm -rf /") == "blocked"

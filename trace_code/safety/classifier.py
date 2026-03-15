from __future__ import annotations

READ_PREFIXES = (
    "ls",
    "cat",
    "head",
    "tail",
    "find",
    "rg",
    "pwd",
    "git status",
    "git log",
    "git diff",
)

BLOCKED_PATTERNS = (
    "rm -rf /",
    "shutdown",
    "reboot",
    ":(){ :|:& };:",
)


def classify_command(command: str) -> str:
    text = command.strip()
    lowered = text.lower()

    if any(pat in lowered for pat in BLOCKED_PATTERNS):
        return "blocked"

    for prefix in READ_PREFIXES:
        if lowered.startswith(prefix):
            return "read"

    return "non_read"

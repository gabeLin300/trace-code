from pathlib import Path


ASSISTANT_DIRS = ("sessions", "logs", "vector_db")


def bootstrap_workspace(root: Path) -> dict[str, Path]:
    assistant_root = root / ".assistant"
    assistant_root.mkdir(parents=True, exist_ok=True)

    created = {"assistant": assistant_root}
    for name in ASSISTANT_DIRS:
        p = assistant_root / name
        p.mkdir(parents=True, exist_ok=True)
        created[name] = p
    return created

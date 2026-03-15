from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionRecord:
    session_id: str
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    chat_history: list[dict[str, Any]] = field(default_factory=list)
    command_history: list[str] = field(default_factory=list)
    tool_history: list[dict[str, Any]] = field(default_factory=list)
    task_plan: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = _now_iso()


class SessionStore:
    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def save(self, record: SessionRecord) -> Path:
        record.touch()
        path = self.path_for(record.session_id)
        path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> SessionRecord:
        path = self.path_for(session_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionRecord(**data)

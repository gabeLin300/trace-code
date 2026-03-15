from __future__ import annotations

from pathlib import Path

from trace_code.cli.banner import render_banner
from trace_code.config import TraceSettings
from trace_code.sessions.store import SessionRecord, SessionStore
from trace_code.workspace.bootstrap import bootstrap_workspace


def start_cli(settings: TraceSettings, no_banner: bool = False, session_id: str = "default") -> dict:
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

    return {
        "banner": banner,
        "resumed": resumed,
        "session_id": session.session_id,
        "sessions_dir": str(dirs["sessions"]),
    }

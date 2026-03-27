from __future__ import annotations

import threading
from typing import Any, Callable


def call_with_timeout(fn: Callable[[], Any], *, timeout_s: float) -> tuple[bool, Any, str]:
    """Run a callable in a daemon thread and return (ok, value, error_text)."""
    state: dict[str, Any] = {"value": None, "error": None}

    def _target() -> None:
        try:
            state["value"] = fn()
        except Exception as exc:  # noqa: BLE001
            state["error"] = exc

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return False, None, f"timeout after {timeout_s:.1f}s"
    if state["error"] is not None:
        return False, None, str(state["error"])
    return True, state["value"], ""

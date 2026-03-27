from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from typing import Any


_CURRENT_SINK: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "trace_code_perf_sink",
    default=None,
)


def get_perf_sink() -> list[dict[str, Any]] | None:
    return _CURRENT_SINK.get()


@contextmanager
def perf_session(sink: list[dict[str, Any]]):
    token = _CURRENT_SINK.set(sink)
    try:
        yield
    finally:
        _CURRENT_SINK.reset(token)


class PerfTrace:
    """Simple span tracer that records elapsed milliseconds into the active sink."""

    def __init__(self, span: str, **meta: Any):
        self.span = span
        self.meta = meta
        self.started = 0.0

    def __enter__(self) -> "PerfTrace":
        self.started = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        sink = get_perf_sink()
        if sink is None:
            return
        elapsed_ms = int((time.monotonic() - self.started) * 1000)
        event: dict[str, Any] = {
            "span": self.span,
            "elapsed_ms": elapsed_ms,
            "timestamp_ms": int(time.time() * 1000),
        }
        if self.meta:
            event.update(self.meta)
        if exc_type is not None:
            event["error"] = str(exc_type.__name__)
        sink.append(event)
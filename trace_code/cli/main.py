from __future__ import annotations

import argparse
import getpass

from trace_code.cli.app import run_interactive_session
from trace_code.cli.preflight import run_preflight
from trace_code.config import TraceSettings
from trace_code.config_init import ensure_initial_config


def main() -> int:
    parser = argparse.ArgumentParser(prog="trace", description="trace-code CLI assistant")
    parser.add_argument("--no-banner", action="store_true", help="Disable ASCII startup banner")
    parser.add_argument("--session-id", default="default", help="Session ID to load/create")
    parser.add_argument("--preflight", action="store_true", help="Run environment readiness checks and exit")
    parser.add_argument(
        "--auto-exec",
        action="store_true",
        help="Auto-execute non-read shell commands without confirmation",
    )
    parser.add_argument("--no-stream", action="store_true", help="Disable streamed CLI response rendering")
    args = parser.parse_args()

    settings = TraceSettings()
    if args.auto_exec:
        settings.safety.confirm_non_read = False
    if args.no_stream:
        settings.ui.stream_responses = False

    def _read() -> str:
        return input("trace> ")

    def _write(text: str) -> None:
        print(text)

    ensure_initial_config(
        settings,
        secret_prompt_fn=getpass.getpass,
        output_fn=_write,
        prompt_if_missing=False,
    )

    report = run_preflight(settings)
    _write(report.render())
    if not report.ok:
        return 2
    if args.preflight:
        return 0

    run_interactive_session(
        settings=settings,
        input_fn=_read,
        output_fn=_write,
        no_banner=args.no_banner,
        session_id=args.session_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

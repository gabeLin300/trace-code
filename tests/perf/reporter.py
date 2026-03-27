from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def _load_entries(paths: list[Path]) -> list[dict]:
    entries: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                entries.append(row)
    return entries


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    return int(ordered[max(0, min(idx, len(ordered) - 1))])


def render_report(entries: list[dict]) -> str:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in entries:
        command = str(row.get("command", "unknown"))
        perf = row.get("perf", [])
        if not isinstance(perf, list):
            continue
        for span in perf:
            if not isinstance(span, dict):
                continue
            name = str(span.get("span", "unknown"))
            elapsed = int(span.get("elapsed_ms", 0))
            grouped[(command, name)].append(elapsed)

    lines = [
        "| command | span | median_ms | p95_ms | stddev_ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for (command, span), values in sorted(grouped.items()):
        median_ms = int(statistics.median(values)) if values else 0
        p95_ms = _percentile(values, 0.95)
        stddev_ms = int(statistics.pstdev(values)) if len(values) > 1 else 0
        lines.append(f"| {command} | {span} | {median_ms} | {p95_ms} | {stddev_ms} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render performance summary table from JSONL files.")
    parser.add_argument("paths", nargs="*", help="JSONL files under tests/perf/results")
    args = parser.parse_args()

    if args.paths:
        paths = [Path(p) for p in args.paths]
    else:
        paths = sorted(Path("tests/perf/results").glob("*.jsonl"))

    entries = _load_entries(paths)
    report = render_report(entries)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

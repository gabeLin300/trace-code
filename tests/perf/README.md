# Performance Baseline

This suite captures reproducible latency spans for representative commands in warm-run mode.

## Representative Commands

- `list files`
- `read file README.md`
- `search web for latest langchain release`
- `search langchain docs for retrieval qa`
- `explain this codebase architecture`

## Warm-Run Definition

Warm runs assume runtime dependencies are already loaded and no process cold-start cost is included.
The baseline test uses deterministic stubs to capture internal phase timing consistency.

## Run Baseline

```bash
pytest tests/perf/test_baseline.py -v
```

Results are written to `tests/perf/results/baseline_YYYYMMDD_HHMMSS.jsonl`.

## Generate Report

```bash
python tests/perf/reporter.py
```

Optional explicit files:

```bash
python tests/perf/reporter.py tests/perf/results/baseline_*.jsonl
```

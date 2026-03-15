from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    delays: tuple[float, ...] = (1.0, 2.0, 4.0)
    jitter_ratio: float = 0.25
    max_single_wait: float = 8.0
    max_total_wait: float = 10.0


def compute_backoff_schedule(policy: RetryPolicy, seed: int = 0) -> list[float]:
    rng = random.Random(seed)
    waits: list[float] = []
    total = 0.0

    for idx in range(max(policy.max_attempts - 1, 0)):
        base = policy.delays[min(idx, len(policy.delays) - 1)]
        jitter = base * policy.jitter_ratio
        wait = base + rng.uniform(-jitter, jitter)
        wait = min(wait, policy.max_single_wait)
        if total + wait > policy.max_total_wait:
            wait = max(0.0, policy.max_total_wait - total)
        waits.append(round(wait, 4))
        total += wait
        if total >= policy.max_total_wait:
            break
    return waits


def execute_with_retry(fn, policy: RetryPolicy, seed: int = 0):
    waits = compute_backoff_schedule(policy, seed=seed)
    attempts = 0
    last_exc = None

    for _ in range(policy.max_attempts):
        attempts += 1
        try:
            return fn(), attempts, waits
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempts >= policy.max_attempts:
                break
    raise RuntimeError(f"retry_exhausted after {attempts} attempts") from last_exc

from trace_code.utils.retry import RetryPolicy, compute_backoff_schedule


def test_retry_schedule_respects_attempt_count() -> None:
    waits = compute_backoff_schedule(RetryPolicy(max_attempts=3), seed=1)
    assert len(waits) == 2


def test_retry_schedule_respects_caps() -> None:
    policy = RetryPolicy(max_attempts=10, max_total_wait=3.0)
    waits = compute_backoff_schedule(policy, seed=2)
    assert sum(waits) <= 3.0
    assert all(w <= policy.max_single_wait for w in waits)

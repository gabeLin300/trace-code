import pytest

from trace_code.utils.retry import RetryPolicy, execute_with_retry


def test_retry_succeeds_after_transient_failures() -> None:
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise ValueError("transient")
        return "ok"

    value, attempts, waits = execute_with_retry(flaky, RetryPolicy(max_attempts=3), seed=1)
    assert value == "ok"
    assert attempts == 3
    assert len(waits) == 2


def test_retry_raises_after_exhaustion() -> None:
    def always_fail():
        raise ValueError("nope")

    with pytest.raises(RuntimeError, match="retry_exhausted"):
        execute_with_retry(always_fail, RetryPolicy(max_attempts=3), seed=1)

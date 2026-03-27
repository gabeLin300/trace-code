from trace_code.cli.app import _drain_stream_buffer


def test_drain_stream_buffer_coalesces_small_token_deltas() -> None:
    ready, pending = _drain_stream_buffer("Hello" + "!" + " How are you today?", max_chunk_chars=180)
    assert ready == []
    assert pending == "Hello! How are you today?"


def test_drain_stream_buffer_flushes_when_too_long() -> None:
    text = ("word " * 80).strip()
    ready, pending = _drain_stream_buffer(text, max_chunk_chars=80)
    assert len(ready) >= 1
    assert all(len(chunk) <= 80 for chunk in ready)
    assert isinstance(pending, str)

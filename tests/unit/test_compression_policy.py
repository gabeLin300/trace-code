from trace_code.context.compression import should_compress, split_history_for_context


def test_compresses_on_turn_threshold() -> None:
    assert should_compress(num_turns=12, prompt_budget_used=0.1)


def test_compresses_on_budget_threshold() -> None:
    assert should_compress(num_turns=2, prompt_budget_used=0.7)


def test_keeps_last_six_turns_in_context() -> None:
    history = [{"turn": i} for i in range(10)]
    older, recent = split_history_for_context(history)
    assert len(older) == 4
    assert len(recent) == 6
    assert recent[0]["turn"] == 4

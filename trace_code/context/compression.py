from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CompressionPolicy:
    turn_threshold: int = 12
    budget_threshold: float = 0.70
    keep_recent_turns: int = 6


def should_compress(num_turns: int, prompt_budget_used: float, policy: CompressionPolicy | None = None) -> bool:
    policy = policy or CompressionPolicy()
    return num_turns >= policy.turn_threshold or prompt_budget_used >= policy.budget_threshold


def split_history_for_context(history: list[dict], policy: CompressionPolicy | None = None) -> tuple[list[dict], list[dict]]:
    policy = policy or CompressionPolicy()
    if len(history) <= policy.keep_recent_turns:
        return [], history
    return history[:-policy.keep_recent_turns], history[-policy.keep_recent_turns:]

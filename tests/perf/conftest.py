from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest


@dataclass(frozen=True)
class RepresentativeCommand:
    name: str
    prompt: str


REPRESENTATIVE_COMMANDS = [
    RepresentativeCommand("list_files", "list files"),
    RepresentativeCommand("read_readme", "read file README.md"),
    RepresentativeCommand("web_langchain_release", "search web for latest langchain release"),
    RepresentativeCommand("docs_retrieval_qa", "search langchain docs for retrieval qa"),
    RepresentativeCommand("explain_architecture", "explain this codebase architecture"),
]


@pytest.fixture
def representative_commands() -> list[RepresentativeCommand]:
    return REPRESENTATIVE_COMMANDS


@pytest.fixture
def perf_results_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path("tests/perf/results") / f"baseline_{stamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

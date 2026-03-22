from trace_code.config import TraceSettings
from trace_code.rag import augment


class _FakeManager:
    def search_langchain_docs(self, query, top_k, collection):
        return {
            "results": [
                {
                    "text": "Use LCEL for composable chains.",
                    "metadata": {"source_url": "https://python.langchain.com/docs/concepts/lcel/"},
                }
            ]
        }

    def web_search(self, query, max_results, search_depth):
        return {
            "answer": "Latest stable LangChain is 0.x.y",
            "results": [
                {
                    "title": "Release Notes",
                    "url": "https://changelog.langchain.com",
                    "content": "Version details",
                }
            ],
        }


def test_should_use_web_search_for_recency_queries() -> None:
    assert augment.should_use_web_search("what is the latest langchain version")
    assert not augment.should_use_web_search("explain RunnableSequence")


def test_build_augmented_prompt_includes_local_context(tmp_path) -> None:
    prompt = augment.build_augmented_prompt(
        "how do I compose chains",
        settings=TraceSettings(workspace_root=tmp_path),
        workspace_root=tmp_path,
        mcp_manager=_FakeManager(),
    )

    assert "Local Knowledge Context" in prompt
    assert "User Question" in prompt
    assert "compose chains" in prompt


def test_build_augmented_prompt_falls_back_to_raw_when_no_context(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(augment, "search_langchain_docs", lambda **kwargs: {"results": []})
    monkeypatch.setattr(augment, "should_use_web_search", lambda query: False)

    raw = "explain retrievers"
    prompt = augment.build_augmented_prompt(
        raw,
        settings=TraceSettings(workspace_root=tmp_path),
        workspace_root=tmp_path,
        mcp_manager=None,
    )

    assert prompt == raw


def test_build_augmented_prompt_includes_web_context_for_latest_queries(tmp_path) -> None:
    prompt = augment.build_augmented_prompt(
        "latest langchain release",
        settings=TraceSettings(workspace_root=tmp_path),
        workspace_root=tmp_path,
        mcp_manager=_FakeManager(),
    )

    assert "Web Search Context" in prompt
    assert "Release Notes" in prompt

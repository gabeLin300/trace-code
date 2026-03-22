import types
import sys
from pathlib import Path

import pytest

from trace_code.knowledge import langchain_docs as kb


def test_crawl_langchain_docs_scoped_and_bounded(monkeypatch) -> None:
    pages = {
        "https://python.langchain.com/docs/introduction/": """
            <html><head><title>Intro</title></head>
            <body>
              <a href='/docs/tutorials/'>Tutorials</a>
              <a href='https://example.com/outside'>Outside</a>
              <p>Hello intro.</p>
            </body></html>
        """,
        "https://python.langchain.com/docs/tutorials/": """
            <html><head><title>Tutorials</title></head>
            <body>
              <p>Tutorial body.</p>
            </body></html>
        """,
    }

    monkeypatch.setattr(kb, "_download", lambda url, timeout_s, user_agent: pages[url])

    docs = kb.crawl_langchain_docs(
        "https://python.langchain.com/docs/introduction/",
        max_pages=2,
    )

    assert len(docs) == 2
    assert docs[0].title == "Intro"
    assert docs[1].url == "https://python.langchain.com/docs/tutorials/"


def test_semantic_split_documents_with_fake_langchain_modules(monkeypatch) -> None:
    fake_docs_mod = types.ModuleType("langchain_core.documents")

    class FakeDocument:
        def __init__(self, page_content, metadata):
            self.page_content = page_content
            self.metadata = metadata

    fake_docs_mod.Document = FakeDocument
    monkeypatch.setitem(sys.modules, "langchain_core.documents", fake_docs_mod)

    class FakeSplitter:
        def split_documents(self, docs):
            return [
                FakeDocument("chunk one", docs[0].metadata),
                FakeDocument("chunk two", docs[0].metadata),
            ]

    monkeypatch.setattr(kb, "_build_semantic_splitter", lambda: FakeSplitter())

    docs = [
        kb.LangChainDoc(
            url="https://python.langchain.com/docs/introduction/",
            title="Intro",
            text="hello world",
            fetched_at="2026-03-21T00:00:00+00:00",
        )
    ]

    chunks = kb.semantic_split_documents(docs)

    assert len(chunks) == 2
    assert chunks[0]["metadata"]["source_url"].startswith("https://python.langchain.com")
    assert chunks[0]["metadata"]["chunk_index"] == 0
    assert chunks[1]["metadata"]["chunk_index"] == 1


def test_index_and_search_langchain_docs_with_fake_chroma(monkeypatch, tmp_path: Path) -> None:
    docs = [
        kb.LangChainDoc(
            url="https://python.langchain.com/docs/introduction/",
            title="Intro",
            text="intro text",
            fetched_at="2026-03-21T00:00:00+00:00",
        )
    ]
    chunks = [
        {
            "id": "id-1",
            "text": "LangChain chains and agents",
            "metadata": {"source_url": docs[0].url, "chunk_index": 0},
        }
    ]

    monkeypatch.setattr(kb, "crawl_langchain_docs", lambda seed_url, max_pages=25: docs)
    monkeypatch.setattr(kb, "semantic_split_documents", lambda _docs: chunks)

    class FakeCollection:
        def __init__(self):
            self.upserted = None

        def upsert(self, ids, documents, metadatas):
            self.upserted = {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            }

        def query(self, query_texts, n_results, include):
            return {
                "documents": [["LangChain chains and agents"]],
                "metadatas": [[{"source_url": docs[0].url}]],
                "distances": [[0.12]],
            }

    fake_collection = FakeCollection()
    monkeypatch.setattr(kb, "_chroma_collection", lambda persist_dir, collection_name: fake_collection)

    index_result = kb.index_langchain_docs(
        seed_url="https://python.langchain.com/docs/introduction/",
        persist_dir=tmp_path / "vector_db",
    )

    assert index_result["status"] == "ok"
    assert index_result["pages_indexed"] == 1
    assert index_result["chunks_indexed"] == 1
    assert fake_collection.upserted is not None

    search_result = kb.search_langchain_docs(
        "how to build chains",
        persist_dir=tmp_path / "vector_db",
        top_k=3,
    )

    assert search_result["status"] == "ok"
    assert search_result["results"][0]["metadata"]["source_url"] == docs[0].url


def test_search_requires_non_empty_query(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        kb.search_langchain_docs("  ", persist_dir=tmp_path)

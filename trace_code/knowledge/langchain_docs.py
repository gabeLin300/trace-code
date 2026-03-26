from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import math
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen


ALLOWED_LANGCHAIN_HOSTS = {
    "python.langchain.com",
    "docs.langchain.com",
    "langchain.com",
}


@dataclass
class LangChainDoc:
    url: str
    title: str
    text: str
    fetched_at: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = " ".join(data.split())
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return "\n".join(self._parts)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_url(url: str, *, base_url: str | None = None) -> str | None:
    candidate = urljoin(base_url, url) if base_url else url
    candidate, _fragment = urldefrag(candidate)
    parsed = urlparse(candidate)

    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.netloc.lower()
    if host not in ALLOWED_LANGCHAIN_HOSTS:
        return None

    clean_path = parsed.path or "/"
    return f"{parsed.scheme}://{host}{clean_path}"


def _extract_title(html: str) -> str:
    start = html.lower().find("<title")
    if start == -1:
        return "LangChain Docs"

    gt = html.find(">", start)
    end = html.lower().find("</title>", gt if gt != -1 else start)
    if gt == -1 or end == -1:
        return "LangChain Docs"

    title_text = html[gt + 1 : end].strip()
    return " ".join(title_text.split()) or "LangChain Docs"


def _extract_links(html: str, page_url: str) -> list[str]:
    links: list[str] = []
    lower = html.lower()
    cursor = 0
    while True:
        anchor = lower.find("<a", cursor)
        if anchor == -1:
            break
        href_pos = lower.find("href", anchor)
        if href_pos == -1:
            cursor = anchor + 2
            continue
        eq = lower.find("=", href_pos)
        if eq == -1:
            cursor = href_pos + 4
            continue

        quote_char = html[eq + 1 : eq + 2]
        if quote_char not in {'"', "'"}:
            cursor = eq + 1
            continue

        end_quote = html.find(quote_char, eq + 2)
        if end_quote == -1:
            cursor = eq + 2
            continue

        raw = html[eq + 2 : end_quote].strip()
        normalized = _normalize_url(raw, base_url=page_url)
        if normalized is not None:
            links.append(normalized)

        cursor = end_quote + 1

    return links


def _extract_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _download(url: str, timeout_s: float, user_agent: str) -> str:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_s) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read()
    return body.decode(charset, errors="replace")


def crawl_langchain_docs(
    seed_url: str,
    *,
    max_pages: int = 25,
    timeout_s: float = 15.0,
    user_agent: str = "trace-code/0.1 (+local-mcp)",
) -> list[LangChainDoc]:
    start_url = _normalize_url(seed_url)
    if start_url is None:
        raise ValueError("seed_url must be an http(s) URL under LangChain documentation hosts")

    queue: list[str] = [start_url]
    seen: set[str] = set()
    docs: list[LangChainDoc] = []

    while queue and len(docs) < max_pages:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)

        try:
            html = _download(current, timeout_s=timeout_s, user_agent=user_agent)
        except Exception:
            continue

        text = _extract_text(html)
        if not text.strip():
            continue

        docs.append(
            LangChainDoc(
                url=current,
                title=_extract_title(html),
                text=text,
                fetched_at=_iso_now(),
            )
        )

        for link in _extract_links(html, current):
            if link not in seen:
                queue.append(link)

    return docs


def _build_semantic_splitter() -> Any:
    try:
        from langchain_experimental.text_splitter import SemanticChunker
    except Exception as exc:
        raise RuntimeError(
            "Semantic splitter unavailable. Install langchain-experimental to enable semantic chunking."
        ) from exc

    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except Exception as exc:
        raise RuntimeError(
            "HuggingFaceEmbeddings unavailable. Install langchain-community and sentence-transformers."
        ) from exc

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return SemanticChunker(embeddings)


def semantic_split_documents(docs: list[LangChainDoc]) -> list[dict[str, Any]]:
    if not docs:
        return []

    try:
        from langchain_core.documents import Document
    except Exception as exc:
        raise RuntimeError("langchain-core is required for semantic chunking") from exc

    splitter = _build_semantic_splitter()

    lc_docs = [
        Document(
            page_content=doc.text,
            metadata={
                "source_url": doc.url,
                "title": doc.title,
                "fetched_at": doc.fetched_at,
            },
        )
        for doc in docs
    ]

    split_docs = splitter.split_documents(lc_docs)
    chunks: list[dict[str, Any]] = []
    for idx, chunk in enumerate(split_docs):
        metadata = dict(chunk.metadata)
        text = chunk.page_content
        chunk_id = hashlib.sha1(f"{metadata.get('source_url','')}::{idx}::{text}".encode("utf-8")).hexdigest()
        chunks.append(
            {
                "id": chunk_id,
                "text": text,
                "metadata": {
                    **metadata,
                    "chunk_index": idx,
                },
            }
        )
    return chunks


def _chroma_collection(persist_dir: Path, collection_name: str):
    try:
        import chromadb
    except Exception as exc:
        raise RuntimeError("chromadb is required for local knowledge indexing") from exc

    client = chromadb.PersistentClient(path=str(persist_dir))
    return client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})


def index_langchain_docs(
    *,
    seed_url: str,
    persist_dir: Path,
    collection_name: str = "langchain_docs",
    max_pages: int = 25,
) -> dict[str, Any]:
    docs = crawl_langchain_docs(seed_url=seed_url, max_pages=max_pages)
    chunks = semantic_split_documents(docs)

    persist_dir.mkdir(parents=True, exist_ok=True)
    collection = _chroma_collection(persist_dir, collection_name)

    if chunks:
        collection.upsert(
            ids=[chunk["id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[chunk["metadata"] for chunk in chunks],
        )

    return {
        "status": "ok",
        "seed_url": seed_url,
        "pages_indexed": len(docs),
        "chunks_indexed": len(chunks),
        "collection": collection_name,
        "persist_dir": str(persist_dir),
    }


def search_langchain_docs(
    query: str,
    *,
    persist_dir: Path,
    collection_name: str = "langchain_docs",
    top_k: int = 4,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")

    collection = _chroma_collection(persist_dir, collection_name)
    fusion_queries = _build_fusion_queries(query)
    per_query_results: list[list[dict[str, Any]]] = []
    for q in fusion_queries:
        result = collection.query(query_texts=[q], n_results=max(top_k, 6), include=["documents", "metadatas", "distances"])
        per_query_results.append(_query_rows_to_items(result))
    items = _reciprocal_rank_fusion(per_query_results, top_k=top_k)

    return {
        "status": "ok",
        "query": query,
        "advanced_retrieval": "fusion",
        "fusion_queries": fusion_queries,
        "results": items,
        "collection": collection_name,
        "persist_dir": str(persist_dir),
    }


def _query_rows_to_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    docs = result.get("documents", [[]])
    metas = result.get("metadatas", [[]])
    dists = result.get("distances", [[]])

    rows: list[dict[str, Any]] = []
    for i, text in enumerate(docs[0] if docs else []):
        metadata = (metas[0][i] if metas and metas[0] and i < len(metas[0]) else {}) or {}
        distance = dists[0][i] if dists and dists[0] and i < len(dists[0]) else None
        rows.append({"text": text, "metadata": metadata, "distance": distance})
    return rows


def _build_fusion_queries(query: str) -> list[str]:
    trimmed = " ".join(query.split())
    variants = [
        trimmed,
        f"{trimmed} tutorial guide",
        f"{trimmed} example code",
        f"{trimmed} best practices",
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for item in variants:
        key = item.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _reciprocal_rank_fusion(result_sets: list[list[dict[str, Any]]], *, top_k: int, k: int = 60) -> list[dict[str, Any]]:
    if not result_sets:
        return []

    scored: dict[str, dict[str, Any]] = {}
    for rows in result_sets:
        for rank, row in enumerate(rows, start=1):
            text = str(row.get("text", "")).strip()
            metadata = row.get("metadata", {}) or {}
            source = str(metadata.get("source_url", ""))
            dedupe_key = f"{source}::{text}"

            slot = scored.setdefault(
                dedupe_key,
                {
                    "text": text,
                    "metadata": metadata,
                    "distance": row.get("distance"),
                    "fusion_score": 0.0,
                },
            )
            slot["fusion_score"] += 1.0 / float(k + rank)

            current_distance = row.get("distance")
            best_distance = slot.get("distance")
            if isinstance(current_distance, (int, float)):
                if not isinstance(best_distance, (int, float)) or current_distance < best_distance:
                    slot["distance"] = float(current_distance)

    ordered = sorted(
        scored.values(),
        key=lambda item: (
            -float(item.get("fusion_score", 0.0)),
            float(item.get("distance")) if isinstance(item.get("distance"), (int, float)) else math.inf,
        ),
    )
    return ordered[:top_k]

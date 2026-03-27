from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from trace_code.knowledge.langchain_docs import index_langchain_docs, search_langchain_docs


DEFAULT_SEED_URL = "https://python.langchain.com/docs/introduction/"


def _default_vector_dir(workspace_root: Path) -> Path:
    return workspace_root / ".assistant" / "vector_db" / "langchain_docs"


def _build_server(workspace_root: Path):
    try:
        FastMCP = importlib.import_module("fastmcp").FastMCP
    except Exception as exc:
        raise RuntimeError("fastmcp is required to run the local knowledge MCP server") from exc

    mcp = FastMCP("trace-local-knowledge")

    @mcp.tool(name="knowledge.ingest_langchain_docs")
    def ingest_langchain_docs(
        seed_url: str = DEFAULT_SEED_URL,
        max_pages: int = 25,
        collection: str = "langchain_docs",
    ) -> dict:
        """Crawl LangChain documentation and index semantically split chunks into ChromaDB."""
        return index_langchain_docs(
            seed_url=seed_url,
            persist_dir=_default_vector_dir(workspace_root),
            collection_name=collection,
            max_pages=max_pages,
        )

    @mcp.tool(name="knowledge.search_langchain_docs")
    def search_docs(
        query: str,
        top_k: int = 4,
        collection: str = "langchain_docs",
    ) -> dict:
        """Query indexed LangChain docs from ChromaDB."""
        return search_langchain_docs(
            query=query,
            persist_dir=_default_vector_dir(workspace_root),
            collection_name=collection,
            top_k=top_k,
        )

    return mcp


def main() -> int:
    parser = argparse.ArgumentParser(prog="trace-local-knowledge", description="Local knowledge MCP server")
    parser.add_argument(
        "--workspace-root",
        default=str(Path.cwd()),
        help="Workspace root where .assistant/vector_db should be stored",
    )
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    server = _build_server(workspace_root)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

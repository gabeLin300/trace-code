# 05 - MCP and RAG Design

## Goal
Define concrete design for tool execution through MCP and retrieval-augmented context flow.

## Scope
- In scope: MCP lifecycle, tool routing, result normalization, RAG pipeline, and index freshness.
- Out of scope: provider-specific embedding micro-optimizations.

## Design

### Implementation Status (2026-03-22)
- Implemented:
  - Filesystem MCP stdio client wiring for `@modelcontextprotocol/server-filesystem` initialize + tools/list + tools/call flow.
  - Filesystem tool execution path (`list files`, `read file`) uses MCP connection logic first.
  - Managed MCP lifecycle manager for filesystem, local knowledge, and web search clients (session startup/shutdown + reconnect-on-failure).
  - Local knowledge MCP and Tavily web search MCP tool-call integration in runtime path.
  - RAG ingestion/index/query baseline for LangChain docs.
  - Advanced RAG technique: Fusion Retrieval (RAG-Fusion style reciprocal-rank fusion of multi-query retrieval).
  - Prompt augmentation path using local knowledge context and recency-triggered web context.
- Not implemented yet:
  - Rich diagnostics around MCP lifecycle events and retry metadata surfacing.
  - RAG index freshness automation (deterministic stale-index detection and rebuild policy).

### MCP Runtime Model (Managed Local Servers)
Supported server mode:
1. **Managed mode**
- trace launches MCP servers as subprocesses from config.
- Performs health checks and reconnection attempts.
- Handles shutdown cleanup on CLI exit.

### MCP Tool Responsibilities
- Filesystem MCP: workspace-scoped file operations.
- Local knowledge MCP: documentation indexing/search interfaces.
- Web search MCP: Tavily-backed web lookup interface, invoked when the agent determines it is needed.

### Tool Routing
- Agent emits a normalized tool request.
- Router selects MCP target by tool namespace and capability metadata.
- Response is normalized into `ToolResult` and appended to session state.

### Error Handling
- Connectivity failures surface actionable tool errors.
- Retry policy for transient network/process errors: up to 3 attempts.
- Backoff defaults: `1s`, `2s`, `4s` delays with +/-25% jitter.
- Cap retries with max single wait `8s` and max total wait budget `10s` per call.
- After retry limit, return an error with retry/backoff metadata and preserve loop integrity.
- Hard failures return non-zero status and preserve loop integrity.

### RAG Pipeline
1. **Ingestion**
- Scan workspace docs (Markdown, HTML, PDF).

2. **Parsing**
- Convert content to normalized text blocks with metadata (path, section, timestamps).

3. **Semantic Chunking**
- Split content into retrieval-friendly chunks.

4. **Embedding Generation**
- Use configured embedding backend.

5. **Vector Storage**
- Persist vectors in Chroma under `.assistant/vector_db`.

6. **Query-time Retrieval**
- Rewrite/expand user query into multiple variants.
- Run top-K vector search per variant.
- Fuse results with reciprocal-rank fusion (RRF) to improve recall and ranking robustness.
- Inject relevant chunks into model context.

### Index Freshness Strategy
- Build index on first run when missing.
- Rebuild or incremental refresh when source docs change or config hash changes.
- Allow manual reindex command in future CLI expansion.

## Acceptance Criteria
- Managed filesystem/local-knowledge/web-search MCP servers function in the same runtime model.
- Tool routing reliably returns normalized results.
- RAG pipeline supports end-to-end ingest and retrieval for supported doc types.
- Index freshness behavior is deterministic and testable.

## Notes
Design prioritizes robust integration boundaries so tooling and retrieval can evolve independently.

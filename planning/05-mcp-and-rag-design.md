# 05 - MCP and RAG Design

## Goal
Define concrete design for tool execution through MCP and retrieval-augmented context flow.

## Scope
- In scope: MCP lifecycle, tool routing, result normalization, RAG pipeline, and index freshness.
- Out of scope: provider-specific embedding micro-optimizations.

## Design

### MCP Runtime Model (Hybrid)
Two supported server modes:
1. **Managed mode**
- trace launches MCP servers as subprocesses from config.
- Performs health checks and reconnection attempts.
- Handles shutdown cleanup on CLI exit.

2. **External mode**
- trace connects to existing MCP endpoints.
- Validates connectivity and tool availability at startup.
- Does not manage remote process lifecycle.

### MCP Tool Responsibilities
- Filesystem MCP: workspace-scoped file operations.
- Local knowledge MCP: documentation indexing/search interfaces.
- Web search MCP: external web lookup interface, invoked when the agent determines it is needed.

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
- Rewrite/expand user query.
- Run top-K vector search.
- Inject relevant chunks into model context.

### Index Freshness Strategy
- Build index on first run when missing.
- Rebuild or incremental refresh when source docs change or config hash changes.
- Allow manual reindex command in future CLI expansion.

## Acceptance Criteria
- Managed and external MCP servers both function in the same deployment model.
- Tool routing reliably returns normalized results.
- RAG pipeline supports end-to-end ingest and retrieval for supported doc types.
- Index freshness behavior is deterministic and testable.

## Notes
Design prioritizes robust integration boundaries so tooling and retrieval can evolve independently.

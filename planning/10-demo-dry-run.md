# 10 - Demo Dry Run

## Goal
Validate two non-trivial workflows before recording the demo, with all three MCP servers visibly invoked.

## Preflight
1. Start `trace`.
2. Run `/health`.
3. Confirm:
- `default: ok` and `fallback: ok`
- `mcp_health=filesystem:True,local_knowledge:True,web_search:True`

## Scenario A (Local RAG + Filesystem)
1. `ingest langchain docs max pages 20`
2. `search langchain docs for retriever and agent memory differences`
3. `list files`
4. `read file README.md`
5. Ask for a short implementation plan using retrieved info and file context.

Expected visible calls:
- `knowledge.ingest_langchain_docs`
- `knowledge.search_langchain_docs`
- `fs.list`
- `fs.read`

## Scenario B (Web + Filesystem + Autonomous Iteration)
1. `search web for latest langchain release notes and key breaking changes`
2. `read file trace_code/agent/loop.py`
3. Ask assistant to propose code changes based on findings and summarize risks.

Expected visible calls:
- `web.search`
- `fs.read`
- Optional additional tool step chosen by autonomous loop

## Rubric Evidence Checklist
- Tool calls are visible in terminal output (`[step] calling tool: ...`).
- At least two non-trivial tasks completed.
- All three MCP server categories shown:
  - filesystem
  - local RAG/knowledge
  - external web search

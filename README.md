# trace-code

`trace-code` is a modular CLI coding assistant design focused on safe tool execution, multi-LLM reasoning, MCP integration, session persistence, and retrieval-augmented context.

## Planning Docs
- [01 - Architecture Overview](planning/01-architecture-overview.md)
- [02 - Technical Spec](planning/02-technical-spec.md)
- [03 - Implementation Roadmap](planning/03-implementation-roadmap.md)
- [04 - Task Backlog](planning/04-task-backlog.md)
- [05 - MCP and RAG Design](planning/05-mcp-and-rag-design.md)
- [06 - Risks, Decisions, Open Questions](planning/06-risks-decisions-open-questions.md)
- [07 - End-to-End Acceptance Scenario](planning/07-end-to-end-acceptance-scenario.md)

## Baseline Decisions
- Vertical-slice MVP
- LangGraph core agent loop
- Hybrid MCP model (managed + external)
- Parallel OpenAI/Ollama/Groq support
- Default model route: Ollama Qwen3
- Default Ollama model tag: `qwen3:8b-instruct`
- Secondary Ollama tag fallback: `qwen3:14b-instruct`
- Fallback model route: Groq `openai/gpt-oss-20b`
- OpenAI models are optional and user-selected
- Confirm non-read commands by default
- Optional read-only safety mode
- Session persistence in `.assistant/sessions/`
- RAG pipeline: parse/chunk/embed/vector search

## Minimal Config Example
```toml
[llm]
default = "ollama:qwen3:8b-instruct"
ollama_fallback = "ollama:qwen3:14b-instruct"
fallback = "groq:openai/gpt-oss-20b"
openai_enabled = false

[mcp]
mode = "hybrid"

[ui]
show_banner = true

[safety]
confirm_non_read = true
read_only = false
```

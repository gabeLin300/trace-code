# 03 - Implementation Roadmap

## Goal
Deliver trace in staged milestones from a vertical-slice MVP to a hardened v1 release.

## Scope
- In scope: milestone sequencing, deliverables, and exit criteria.
- Out of scope: sprint-level staffing or calendar commitments.

## Design

### Status Snapshot (2026-03-22)
- Completed:
  - Milestone 1 core scaffolding is implemented (CLI entrypoint, routing, built-ins, session persistence, startup banner toggle, default/fallback provider manager, filesystem MCP tool execution).
  - Unit and integration test foundation is implemented and passing.
  - Managed MCP session lifecycle manager is implemented for filesystem, local knowledge, and Tavily web search servers.
  - LangChain docs RAG ingestion and retrieval paths are implemented.
  - Fusion Retrieval (advanced RAG technique) is implemented for local knowledge search.
  - Prompt augmentation is implemented for non-tool LLM turns (local knowledge context + recency-triggered web context).
  - Bounded autonomous multi-step task loop is implemented (tool execution + LLM decide-next-step iteration).
  - Safety gate v1 runtime behavior is implemented (blocked and requires-confirmation statuses for shell commands).
  - CLI startup UX enhancements are implemented (workspace/provider/model header, session resume/new prompt, tool-call indicator output).
  - One-time API key initialization flow is implemented (loads `.env`, prompts for missing keys, persists to `.env`).
  - Planning diagram artifacts were added (state diagram and multi-scenario sequence diagrams).
- In progress:
  - Reliability and diagnostics hardening for MCP and tool execution paths.
- Remaining:
  - Session compression in the live model-facing context path.
  - RAG index freshness/rebuild policy automation.
  - Observability and reliability hardening.
  - Milestone 1 e2e acceptance automation and release matrix CI gates.

### Milestone 1 - Vertical Slice MVP
Deliverables:
- CLI shell with command routing and built-ins (`/help`, `/config`, `/sessions`, `/exit`).
- Startup ASCII logo/banner with config and flag-based disable behavior for non-interactive use.
- Workspace bootstrap and `.assistant` directory creation.
- Session persistence/load flows.
- LangGraph core agent loop with tool/no-tool branching.
- Managed MCP manager foundation for filesystem, local knowledge, and web search servers.
- Shell safety baseline (confirm non-read by default, dangerous command blocking).

Exit Criteria:
- User can run `trace`, start/resume a session, and complete a simple tool-assisted task.
- Session files persist and reload correctly.
- Non-read commands require explicit confirmation.
- Milestone 1 e2e acceptance scenario passes (startup banner -> session create -> read tool call -> summary -> session reload).

### Milestone 2 - MCP + RAG Depth
Deliverables:
- Filesystem, local knowledge, and web search MCP routing.
- RAG ingestion pipeline (parse/chunk/embed/store) for Markdown/HTML/PDF.
- Query-time retrieval and prompt augmentation.
- Index freshness checks (missing/stale index handling).
- Integration test suite for MCP routing, retry behavior, and RAG retrieval quality baselines.

Exit Criteria:
- RAG-backed queries return contextually relevant augmented responses.
- MCP tool calls are logged and recover gracefully from transient failures.
- Freshness strategy is automated and verified by tests.

### Milestone 3 - Hardening and Release Readiness
Deliverables:
- Provider parity improvements for OpenAI/Ollama/Groq adapters.
- Observability: structured logs, tool timing, error traces.
- Robust test coverage across CLI, agent loop, session persistence, MCP, safety, and RAG.
- Release matrix validation:
  - Groq `llama-3.3-70b-versatile` (default): full end-to-end suite.
  - Groq `llama-3.1-8b-instant` (fallback): core + tool-calling + safety suite.
  - Ollama (optional): smoke + tool-calling contract suite.
  - OpenAI (optional): smoke + tool-calling contract suite.
- Documentation polish and onboarding quickstart.

Exit Criteria:
- End-to-end smoke tests pass reliably.
- Failures surface actionable diagnostics.
- README and planning docs align with implemented behavior.

## Acceptance Criteria
- Milestones are dependency-ordered and executable.
- Each milestone has measurable exit criteria.
- Roadmap stays aligned to the locked architectural defaults.

## Notes
Roadmap prioritizes usable capability early, then subsystem depth, then quality hardening.

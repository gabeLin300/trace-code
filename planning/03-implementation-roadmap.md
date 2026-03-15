# 03 - Implementation Roadmap

## Goal
Deliver trace in staged milestones from a vertical-slice MVP to a hardened v1 release.

## Scope
- In scope: milestone sequencing, deliverables, and exit criteria.
- Out of scope: sprint-level staffing or calendar commitments.

## Design

### Milestone 1 - Vertical Slice MVP
Deliverables:
- CLI shell with command routing and built-ins (`/help`, `/config`, `/sessions`, `/exit`).
- Startup ASCII logo/banner with config and flag-based disable behavior for non-interactive use.
- Workspace bootstrap and `.assistant` directory creation.
- Session persistence/load flows.
- LangGraph core agent loop with tool/no-tool branching.
- Hybrid MCP manager foundation (managed + external wiring).
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

### Milestone 3 - Hardening and Release Readiness
Deliverables:
- Provider parity improvements for OpenAI/Ollama/Groq adapters.
- Observability: structured logs, tool timing, error traces.
- Robust test coverage across CLI, agent loop, session persistence, MCP, safety, and RAG.
- Release matrix validation:
  - Ollama Qwen3: full end-to-end suite.
  - Groq `openai/gpt-oss-20b`: core + tool-calling + safety suite.
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

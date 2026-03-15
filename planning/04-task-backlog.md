# 04 - Task Backlog

## Goal
Define an actionable, prioritized backlog to implement trace with clear acceptance criteria.

## Scope
- In scope: engineering tasks grouped by priority (`Now`, `Next`, `Later`).
- Out of scope: release scheduling and people assignment.

## Design

### Now
1. Project scaffolding
- Create package structure and dependency baseline.
- Acceptance: repo installs cleanly and CLI entrypoint is runnable.

2. CLI routing and built-ins
- Implement `/help`, `/config`, `/sessions`, `/exit`; route unknown input to agent.
- Acceptance: command parsing is deterministic and tested.

3. CLI startup branding
- Render an ASCII `trace` logo/banner at startup.
- Add config `ui.show_banner` and runtime flag `--no-banner` to disable banner.
- Acceptance: banner displays in interactive runs and is disabled when configured/flagged.

4. Workspace/session bootstrap
- Detect workspace root and initialize `.assistant/{sessions,logs,vector_db}`.
- Acceptance: first run creates required directories and session file.

5. Default config template
- Publish a minimal config example with pinned model route, fallback route, UI banner, MCP mode, and safety defaults.
- Acceptance: README contains a copy-paste config block that matches technical spec defaults.

6. Session persistence contracts
- Implement `SessionRecord` read/write/update behavior.
- Acceptance: session resume reproduces prior chat/tool history.

7. LangGraph loop core
- Implement context build, model call, tool decision, tool execution, and iteration states.
- Acceptance: tool and non-tool paths both complete successfully.

8. Safety gate v1
- Confirm all non-read commands; enforce dangerous-command blocklist.
- Acceptance: blocked/confirmation-required status is returned in `ToolResult`; read allowlist defaults execute without confirmation.

9. Unit test foundation
- Add unit tests for config parsing, command routing, session serialization, compression policy, retry/backoff schedule, shell classifier, and provider normalization contracts.
- Acceptance: unit suite runs in CI and covers all listed modules.

### Next
1. Provider adapters
- Add OpenAI, Ollama, and Groq adapters under common interface.
- Acceptance: all adapters pass shared contract tests.

2. Hybrid MCP manager
- Add managed subprocess lifecycle and external endpoint attach logic.
- Acceptance: can run one managed and one external MCP server in same session.

3. Tool router integration
- Route filesystem, local knowledge, and web search calls via MCP.
- Acceptance: normalized tool results logged to session.

4. RAG indexing/retrieval baseline
- Implement ingestion, parsing, chunking, embedding, Chroma storage, and top-K retrieval.
- Acceptance: retrieval injects relevant context into prompt for sample docs.

5. Session compression policy implementation
- Auto-compress model-facing history every 12 turns or at 70% prompt budget, while preserving 6 recent raw turns.
- Acceptance: prompts stay within budget and raw session files remain lossless.

6. Milestone 1 e2e acceptance scenario
- Implement the baseline acceptance flow (startup banner, session create, read tool call, summary, reload).
- Acceptance: scenario passes in automated smoke test and manual verification.

7. Integration test suite
- Add integration tests for CLI startup UX, workspace bootstrap, session reload, agent loop branching, MCP routing, and transient failure retries.
- Acceptance: integration suite passes with deterministic fixtures/test doubles.

### Later
1. Observability and diagnostics
- Structured logs, correlation IDs, and per-tool timing dashboards.
- Acceptance: key runtime events are traceable across one session.

2. Reliability enhancements
- Retry/backoff for flaky MCP endpoints and web search errors.
- Acceptance: transient failures degrade gracefully with user-visible status.

3. Release matrix enforcement
- Add CI/quality gates for Ollama full e2e, Groq core/tool/safety, and OpenAI smoke/contract tests.
- Acceptance: release pipeline fails if required provider matrix checks do not pass.

4. UX polish
- Improved rich UI for plan previews, tool output diffing, and confirmations.
- Acceptance: command flow remains clear during multi-step tasks.

## Acceptance Criteria
- Backlog is prioritized and sequenced by dependency.
- Every task includes a concrete, testable acceptance condition.
- Task list aligns with roadmap milestones and technical contracts.

## Notes
This backlog is intentionally compact and implementation-ready for early execution.

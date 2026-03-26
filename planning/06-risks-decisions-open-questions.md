# 06 - Risks, Decisions, Open Questions

## Goal
Capture locked design choices, major risks, mitigation plans, and unresolved questions requiring future decisions.

## Scope
- In scope: architecture and delivery risks for v1.
- Out of scope: long-term product roadmap beyond initial release.

## Design

### Locked Decisions
- MVP strategy: **vertical slice**.
- Agent orchestration: **LangGraph core loop**.
- MCP model: **managed local subprocess servers** (filesystem, LangChain docs, Tavily web search).
- LLM providers: **parallel support** for OpenAI, Ollama, and Groq.
- Default model route: **Groq `llama-3.3-70b-versatile`**.
- Fallback route: **Groq `llama-3.1-8b-instant`**.
- Ollama usage: **optional**, only when explicitly selected by user/config.
- OpenAI usage: **optional**, only when explicitly selected by user/config.
- Safety default: **confirm all non-read commands**.
- Optional safety override: **read-only mode** for fully non-mutating workflows.
- Session persistence location: `.assistant/sessions/`.
- RAG model: parse -> chunk -> embed -> vector search (top-K augmentation).
- Advanced RAG technique: Fusion Retrieval (RAG-Fusion with reciprocal-rank fusion over multiple rewritten queries).
- Web search policy: **enabled when needed** by the agent/tool router.
- MCP retry policy: **at most 3 attempts** with `1s/2s/4s` backoff, +/-25% jitter, `8s` max single wait, and `10s` max total wait budget per call.
- Shell safety classification defaults:
  - Read allowlist: `ls`, `cat`, `head`, `tail`, `find`, `rg`, `pwd`, `git status`, `git log`, `git diff`.
  - Non-read: commands that write files, mutate git state, install dependencies, or run side-effectful scripts.
- Session compression policy: **auto-compress every 12 turns or at 70% prompt budget**, while keeping the most recent 6 turns raw in prompt context.
- History retention policy: **never delete raw session history on disk**; compression applies only to model-facing context.
- Release test matrix policy:
  - Groq `llama-3.3-70b-versatile` (default path): full end-to-end suite.
  - Groq `llama-3.1-8b-instant` (fallback path): core + tool-calling + safety suite.
  - Ollama (optional path): smoke + tool-calling contract suite.
  - OpenAI (optional path): smoke + tool-calling contract suite.
- Milestone 1 acceptance scenario policy: startup banner -> session create -> read tool call -> summary -> session reload must pass before phase completion.
- Testing policy: use unit + integration + e2e pyramid, with provider release-gate matrix as the hard release criterion.

### Risk Register
1. Provider behavior drift
- Risk: output/tool-call shape differences across providers.
- Mitigation: strict normalized response adapter contract with conformance tests.

2. MCP availability and reliability
- Risk: server startup failure, process instability, tool discovery mismatch.
- Mitigation: health checks, retries, startup diagnostics, and clear degraded-mode messaging.

3. Unsafe command execution
- Risk: accidental destructive actions.
- Mitigation: confirmation gate for non-read commands, blocklist, optional read-only mode.

4. Context window pressure
- Risk: excessive history or retrieved context causing degraded reasoning.
- Mitigation: token budgeting, pruning strategy, retrieval cap tuning.

5. RAG relevance quality
- Risk: poor chunking or embeddings reduce answer quality.
- Mitigation: tune chunk size/overlap, query rewriting, and regression queries for validation.

### Open Questions
- No unresolved blocking questions at this time.

### Current Gaps (Execution Tracking)
- Managed MCP lifecycle still needs hardening (diagnostics and richer recovery behavior).
- RAG freshness automation is still pending (missing/stale rebuild strategy in runtime).
- Session compression policy is locked in plan but not yet wired into live context build path.
- Provider auth diagnostics still need hardening (explicit detection/reporting for `.env`/runtime key mismatches causing Groq 403 responses).
- Release matrix CI enforcement and observability stack are still pending.

## Acceptance Criteria
- Decisions are explicit and cross-document consistent.
- Each high-impact risk includes at least one concrete mitigation.
- Open questions are actionable and scoped for future decision meetings.

## Notes
This document should be updated whenever a decision is locked or a major risk profile changes.

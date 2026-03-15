# 02 - Technical Spec

## Goal
Define the implementation contracts, runtime interfaces, and behavior-level requirements for trace v1.

## Scope
- In scope: configuration schema, session schema, tool result contract, agent state machine, provider interfaces, MCP and safety behavior.
- Out of scope: non-critical optional features and post-v1 optimizations.

## Design

### CLI Contract
Built-in commands:
- `/help`: Show usage and command list.
- `/config`: Show effective config and key status (masked).
- `/sessions`: List, inspect, and resume sessions.
- `/exit`: End interactive loop gracefully.

All non-built-in input is sent to the agent loop.

Startup UX:
- Render an ASCII `trace` logo/banner at interactive CLI startup.
- Support disabling banner via config (`ui.show_banner=false`) and runtime flag (`--no-banner`) for automation/scripting.

### Config Contract (`TraceSettings`)
Required top-level groups:
- `workspace`: root detection and `.assistant` path behavior.
- `llm`: provider selection and model config for OpenAI/Ollama/Groq.
  - Default model route: Ollama `qwen3:8b-instruct` (pinned tag for reproducibility).
  - Secondary Ollama fallback tag (if default unavailable): `qwen3:14b-instruct`.
  - Fallback route: Groq `openai/gpt-oss-20b`.
  - OpenAI models are optional and used only when explicitly selected by the user/config.
- `mcp`: server definitions with `mode` (`managed` or `external`), startup command or endpoint.
- `ui`: CLI presentation settings (including `show_banner`).
- `web_search`: enablement and invocation policy (`when_needed` default).
- `retry`: transient tool retry settings (`max_attempts=3`) and fixed defaults:
  - delay schedule: `1s`, `2s`, `4s` (exponential)
  - jitter: +/-25%
  - max single wait: `8s`
  - max total retry wait budget per call: `10s`
- `safety`: `confirm_non_read` (default true), `read_only` (default false), blocked patterns.
- `rag`: ingest targets, chunking settings, embedding provider, `top_k`.
- `sessions`: active session behavior and persistence path.

### Session Contract (`SessionRecord`)
Persist in `.assistant/sessions/<session_id>.json`:
- `session_id`
- `created_at`, `updated_at`
- `chat_history[]`
- `command_history[]`
- `tool_history[]`
- `task_plan`
- `metadata` (provider/model/config snapshot summary)

Session compression behavior:
- Auto-compress model-facing history every 12 turns, or earlier when prompt budget exceeds 70%.
- Keep the most recent 6 turns uncompressed in model context.
- Preserve full raw history on disk; compression never deletes stored session records.

### Tool Result Contract (`ToolResult`)
Normalized return shape from all tools:
- `tool_name`
- `status` (`ok`, `error`, `blocked`, `requires_confirmation`)
- `stdout`
- `stderr`
- `artifacts` (optional structured data)
- `duration_ms`
- `timestamp`

### Agent State Machine (LangGraph)
Primary states:
1. `build_context`
2. `enforce_token_budget`
3. `reason_with_model`
4. `decide_tool_or_answer`
5. `execute_tool` (conditional)
6. `append_result_to_session`
7. `complete_or_iterate`

Behavior:
- If tool is requested, route through tool router and append structured results.
- If no tool is required, produce final answer and persist turn state.
- Iteration continues until completion criteria or guard limits are reached.

### LLM Provider Interface
Provider adapters must expose a shared contract:
- `validate_config()`
- `generate(messages, tool_schema, settings)`
- `normalize_response(raw)`

Supported providers in v1:
- Ollama (default): `qwen3:8b-instruct`
- Groq (fallback): `openai/gpt-oss-20b`
- OpenAI (optional): only when explicitly selected

All providers must map to a common response format for the agent loop.

Release gate test matrix:
- Ollama Qwen3 (default): full end-to-end suite.
- Groq `openai/gpt-oss-20b` (fallback): core + tool-calling + safety suite.
- OpenAI (optional): smoke + tool-calling contract suite.

### MCP Integration (Hybrid)
- `managed`: trace starts, monitors, and stops subprocess MCP servers.
- `external`: trace attaches to user-provided endpoint(s).
- Tool router dispatches requests to filesystem, local knowledge, or web search capabilities.
- Web search is enabled when needed based on agent/tool-routing decision.
- Transient MCP/tool failures retry up to 3 attempts with `1s/2s/4s` delays, +/-25% jitter, `8s` single-wait cap, and `10s` total-wait cap.

### Safety Rules
- Default: confirm all non-read shell/file mutating actions.
- Optional `read_only=true`: deny mutating tool calls.
- Blocklist rejects known destructive patterns.
- Filesystem access must remain within workspace root.
- Read-command allowlist defaults:
  - `ls`, `cat`, `head`, `tail`, `find`, `rg`, `pwd`, `git status`, `git log`, `git diff`
- Non-read classification:
  - Any command that writes files, mutates git state, installs dependencies, or executes side-effectful scripts.

### Testing Strategy
Use a test pyramid: many unit tests, focused integration tests, and a small e2e release-gate suite.

Unit tests (fast, broad):
- `TraceSettings` parsing/validation and default resolution.
- CLI command routing (`/help`, `/config`, `/sessions`, `/exit`, unknown -> agent).
- `SessionRecord` serialization/deserialization and update behavior.
- Context compression policy (12 turns, 70% threshold, keep last 6 raw turns).
- Retry/backoff schedule and cap enforcement (`1s/2s/4s`, jitter bounds, wait caps).
- Shell safety classifier (read allowlist, non-read confirmation, blocked patterns).
- Provider adapter response normalization and contract conformance.

Integration tests (critical subsystem paths):
- CLI startup behavior (banner shown by default, disabled by config/flag).
- Workspace bootstrap and `.assistant` directory initialization.
- Session create -> persist -> reload consistency.
- Agent loop tool-call and no-tool branches.
- MCP routing across filesystem/local-knowledge/web-search with test doubles.
- Retry behavior under transient MCP/tool failure scenarios.

End-to-end smoke tests (release gates):
- Milestone 1 baseline interactive flow from `07-end-to-end-acceptance-scenario.md`.
- Provider matrix gates:
  - Ollama `qwen3:8b-instruct`: full e2e suite.
  - Groq `openai/gpt-oss-20b`: core + tool-calling + safety suite.
  - OpenAI (optional): smoke + tool-calling contract suite.

## Acceptance Criteria
- Contracts are explicit enough to implement without new design decisions.
- Agent state transitions are defined and cover tool/no-tool paths.
- Safety defaults are concrete and enforceable.
- Provider and MCP abstractions support consistent runtime behavior.

## Notes
This spec intentionally favors implementation clarity for a vertical-slice MVP while retaining modular boundaries for future enhancements.

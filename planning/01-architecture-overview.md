# 01 - Architecture Overview

## Goal
Define the high-level architecture for `trace`, a modular CLI coding assistant that operates in any workspace with strong safety, session persistence, and retrieval-augmented reasoning.

## Scope
- In scope: CLI interaction model, preflight/startup gate, agent loop, session/context management, MCP tool execution, RAG pipeline, startup and runtime flow.
- Out of scope: low-level class-by-class implementation details (covered in technical spec/backlog).

## Design

### System Layers
1. **User Interface (CLI)**
- Handles command input and interactive prompts.
- Supports built-ins: `/help`, `/config`, `/sessions`, `/health`, `/exit`.
- Routes unknown commands to the agent loop.
- Displays tool calls, action summaries, and outcomes.
- Renders an ASCII `trace` logo on startup (configurable for non-interactive/scripting use).
- Supports `--preflight` mode for one-shot readiness checks (non-interactive).

2. **Startup / Preflight Gate**
- Validates required API keys and MCP prerequisites before REPL entry.
- Runs strict checks for `npx`, filesystem MCP launchability, local knowledge MCP launchability, and web MCP launchability.
- Fails fast with categorized diagnostics and remediation guidance when checks fail.

3. **Agent / Reasoning Layer**
- Uses a bounded autonomous loop: context build -> tool/answer decision -> execute -> iterate until done/limit.
- Supports no-tool and tool-call branches.
- Includes planning capability for multi-step tasks.
- Emits explicit loop stop reasons for observability and safety guardrail evidence.
- Planner receives both typed tools and discovered MCP tool inventory.

4. **Context and Session Management**
- Persists session state in `.assistant/sessions/` as JSON.
- Stores chat history, command history, tool results, and task-plan state.
- Applies retrieval-based context augmentation before model calls (local knowledge + optional web context).

5. **Tool Execution Layer (MCP + local wrappers)**
- Uses managed local MCP subprocess servers (started/stopped by trace).
- Routes tool calls to filesystem, local knowledge, and web search capabilities.
- Local wrappers support shell execution with safety policies.
- Supports hybrid dynamic tool loading:
  - Typed deterministic tools (`fs.*`, `knowledge.*`, `web.search`, `shell.exec`)
  - Generic dynamic MCP invocation via `mcp.call(server, tool, arguments)`
- MCP diagnostics classify failures (`missing_key`, `missing_binary`, `startup_timeout`, `server_crash`) and expose remediations.

6. **Knowledge Retrieval (RAG)**
- Uses a local knowledge MCP server targeting LangChain documentation.
- Ingests, semantically chunks, embeds, and stores vectors in Chroma.
- Retrieves top-K relevant chunks to augment model prompts.
- Includes advanced RAG behavior (Fusion Retrieval style ranking in the knowledge pipeline).

### Core Runtime Flow
1. User runs `trace`.
2. CLI renders startup banner/logo unless disabled by config/flag.
3. Workspace is detected from current directory.
4. `.assistant/` directories are created if missing.
5. Config and API keys are loaded.
6. Preflight runs and validates required dependencies + MCP launchability.
7. If preflight fails, CLI exits with actionable remediation.
8. MCP servers are started (managed mode) for interactive session.
9. Session is resumed or initialized.
10. Agent loop processes user requests until completion/exit.

### Safety Model
- Filesystem actions are scoped to workspace root.
- Shell default policy: confirm all non-read commands.
- Dangerous command patterns are blocked.
- Optional read-only mode prevents mutating actions.

## Acceptance Criteria
- Architecture clearly separates responsibilities across CLI, startup gate, agent, context/session, tool routing, and RAG.
- Startup and runtime flow are explicit, fail-fast, and implementable.
- Safety defaults are specified and consistent with other planning docs.
- Managed MCP model, hybrid dynamic MCP tool support, and multi-LLM support are represented at the architecture level.

## Notes
This architecture is optimized for a vertical-slice MVP while preserving extension points for deeper automation, additional tools, and provider evolution.

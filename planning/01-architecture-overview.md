# 01 - Architecture Overview

## Goal
Define the high-level architecture for `trace`, a modular CLI coding assistant that operates in any workspace with strong safety, session persistence, and retrieval-augmented reasoning.

## Scope
- In scope: CLI interaction model, agent loop, session/context management, MCP tool execution, RAG pipeline, startup and runtime flow.
- Out of scope: low-level class-by-class implementation details (covered in technical spec/backlog).

## Design

### System Layers
1. **User Interface (CLI)**
- Handles command input and interactive prompts.
- Supports built-ins: `/help`, `/config`, `/sessions`, `/exit`.
- Routes unknown commands to the agent loop.
- Displays tool calls, action summaries, and outcomes.
- Renders an ASCII `trace` logo on startup (configurable for non-interactive/scripting use).

2. **Agent / Reasoning Layer**
- Uses a bounded autonomous loop: context build -> tool/answer decision -> execute -> iterate until done/limit.
- Supports no-tool and tool-call branches.
- Includes planning capability for multi-step tasks.
- Emits explicit loop stop reasons for observability and safety guardrail evidence.

3. **Context and Session Management**
- Persists session state in `.assistant/sessions/` as JSON.
- Stores chat history, command history, tool results, and task-plan state.
- Applies token budget management and context pruning before model calls.

4. **Tool Execution Layer (MCP + local wrappers)**
- Uses managed local MCP subprocess servers (started/stopped by trace).
- Routes tool calls to filesystem, local knowledge, and web search capabilities.
- Local wrappers support shell execution and planning actions.

5. **Knowledge Retrieval (RAG)**
- Ingests workspace docs (Markdown, HTML, PDF).
- Parses/chunks content semantically.
- Embeds chunks and stores vectors in Chroma.
- Retrieves top-K relevant chunks to augment model prompts.

### Core Runtime Flow
1. User runs `trace`.
2. CLI renders startup banner/logo unless disabled by config/flag.
3. Workspace is detected from current directory.
4. `.assistant/` directories are created if missing.
5. Config and API keys are loaded/validated.
6. MCP servers are started (managed mode).
7. Session is resumed or initialized.
8. RAG index is built or refreshed when needed.
9. Agent loop processes user requests until completion/exit.

### Safety Model
- Filesystem actions are scoped to workspace root.
- Shell default policy: confirm all non-read commands.
- Dangerous command patterns are blocked.
- Optional read-only mode prevents mutating actions.

## Acceptance Criteria
- Architecture clearly separates responsibilities across CLI, agent, context/session, tool routing, and RAG.
- Startup and runtime flow are explicit and implementable.
- Safety defaults are specified and consistent with other planning docs.
- Managed MCP model and multi-LLM support are represented at the architecture level.

## Notes
This architecture is optimized for a vertical-slice MVP while preserving extension points for deeper automation, additional tools, and provider evolution.

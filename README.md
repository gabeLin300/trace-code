# trace-code

`trace-code` is a CLI coding assistant with:
- Filesystem tools (workspace-scoped)
- LangChain docs retrieval (local vector index)
- Advanced RAG: Fusion Retrieval (RAG-Fusion style reciprocal-rank fusion)
- Tavily web search
- Session persistence in `.assistant/sessions/`
- Safety confirmations for non-read shell commands

## Requirements
- Python 3.11+
- Node.js + `npx` (used by filesystem MCP server)
- Groq API key (default model route uses Groq)
- Optional provider/API keys:
  - `GROQ_API_KEY` (required for default/fallback LLM routes)
  - `OLLAMA_BASE_URL` (only if you reconfigure to Ollama)
  - `OPENAI_API_KEY` (if using OpenAI)
  - `TAVILY_API_KEY` (for web search)

## Install
```bash
git clone <repo-url>
cd <repo-folder>
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e .
```

If your environment does not resolve all extras from `pyproject.toml`, install:
```bash
pip install -r requirements.txt
```

## Run
```bash
trace
```

MCP preflight (optional but recommended before `trace`):
```bash
npx --version
python -m trace_code.mcp.local_knowledge_server --help
python -m trace_code.mcp.web_search_server --no-prompt --help
```

Useful flags:
```bash
trace --session-id main
trace --no-banner
```

On first startup, `trace` checks for required API keys in `.env` (and current environment).  
If missing, it prompts you once and writes provided values into `.env` in your current workspace.

## Built-in Commands
- `/help`
- `/config`
- `/sessions`
- `/health`
- `/exit`

## Usage Examples
Filesystem:
- `list files`
- `read file README.md`

LangChain docs knowledge:
- `ingest langchain docs max pages 30`
- `search langchain docs for retrieval qa`

Web search:
- `search web for latest langchain release`

Shell with safety:
- `run command git status` (read command, runs directly)
- `run command touch demo.txt` (returns confirmation required)
- `confirm run command touch demo.txt` (runs after confirmation)

## Data Locations
- Sessions: `.assistant/sessions/`
- Logs: `.assistant/logs/`
- Vector store: `.assistant/vector_db/`

## Troubleshooting
- `trace: command not found`
  - Make sure the virtual environment is active: `source .venv/bin/activate`
  - Reinstall entrypoint: `pip install -e .`

- `pytest` or package import errors after install
  - Install full dependency set: `pip install -r requirements.txt`

- Filesystem tool errors mentioning MCP server startup
  - Ensure Node.js and `npx` are installed and available in `PATH`.
  - Test `npx` manually: `npx --version`

- Web search fails with missing Tavily key
  - Set `TAVILY_API_KEY` in your shell, or run search once and enter key when prompted.
  - Non-interactive mode uses `--no-prompt`, so key must already be set.

- No results from LangChain docs search
  - Run ingestion first: `ingest langchain docs max pages 30`
  - Then query: `search langchain docs for <topic>`

- Slow first-time RAG indexing
  - First run may download embedding/model assets; subsequent runs are faster.

## Uninstall
If installed in a project virtual environment:

```bash
cd <repo-folder>
source .venv/bin/activate
pip uninstall trace-code
deactivate
```

To fully remove the local environment and repo files:

```bash
cd <parent-folder>
rm -rf <repo-folder>
```

Optional: remove generated assistant data from any workspace where you ran `trace`:

```bash
rm -rf /path/to/workspace/.assistant
```
## LucidChart Flow Diagram
[Link to Diagram](https://lucid.app/lucidchart/45312233-6c52-4ff2-9d3d-13bd0d5d9b68/edit?viewport_loc=468%2C209%2C2796%2C1267%2C0_0&invitationId=inv_47aad19a-b165-4232-8ff4-b5352fa0a906)

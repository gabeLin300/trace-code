# trace-code

`trace-code` is a CLI coding assistant with:
- Filesystem tools (workspace-scoped)
- LangChain docs retrieval (local vector index)
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

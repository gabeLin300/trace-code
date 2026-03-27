from __future__ import annotations

from pathlib import Path
import os
from typing import Callable

from trace_code.config import TraceSettings


def ensure_initial_config(
    settings: TraceSettings,
    *,
    secret_prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    prompt_if_missing: bool = True,
) -> None:
    """Load .env and prompt for missing required API keys."""
    workspace_root = Path(settings.workspace_root)
    env_path = _resolve_env_path(workspace_root)
    output_fn(f"Config: using env file {env_path}")

    env_values = _load_env_values(env_path)

    # Load .env values into process env for this runtime.
    for key, value in env_values.items():
        if key and value:
            os.environ[key] = value

    required = required_api_keys(settings)
    missing: list[str] = []
    for key in required:
        value = os.getenv(key, "").strip() or env_values.get(key, "").strip()
        if not value:
            missing.append(key)

    if not missing:
        return

    if not prompt_if_missing:
        return

    output_fn("Initial setup: missing API keys detected. You'll be prompted once and values will be saved to .env.")

    updates: dict[str, str] = {}
    for key in missing:
        value = secret_prompt_fn(f"Enter {key}: ").strip()
        if not value:
            output_fn(f"Skipped {key} (left empty).")
            continue
        updates[key] = value
        os.environ[key] = value

    if updates:
        _upsert_env_file(env_path, updates)
        # Reload to ensure process env reflects persisted values.
        for key, value in updates.items():
            os.environ[key] = value
        output_fn(f"Saved {len(updates)} key(s) to {env_path}.")


def required_api_keys(settings: TraceSettings) -> list[str]:
    keys: list[str] = []

    providers = {
        settings.llm.default.split(":", 1)[0],
        settings.llm.fallback.split(":", 1)[0],
    }

    if "groq" in providers:
        keys.append("GROQ_API_KEY")

    if "openai" in providers and settings.llm.openai_enabled:
        keys.append("OPENAI_API_KEY")

    if settings.web_search.enabled:
        keys.append(settings.web_search.api_key_env_var)

    # Stable order for UX/tests
    return sorted(dict.fromkeys(keys))


def _resolve_env_path(workspace_root: Path) -> Path:
    # Prefer workspace .env. If missing, fall back to current working directory .env.
    workspace_env = workspace_root / ".env"
    if workspace_env.exists():
        return workspace_env
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
    return workspace_env


def _load_env_values(path: Path) -> dict[str, str]:
    try:
        from dotenv import dotenv_values, load_dotenv
    except Exception:
        return _read_env_file(path)

    # Use selected .env as source of truth for this run.
    load_dotenv(dotenv_path=path, override=True)
    raw = dotenv_values(path)
    values: dict[str, str] = {}
    for key, value in raw.items():
        if key and value:
            values[key] = str(value)
    return values


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    out_lines: list[str] = []

    for raw in existing_lines:
        if "=" not in raw or raw.strip().startswith("#"):
            out_lines.append(raw)
            continue
        key = raw.split("=", 1)[0].strip()
        if key in remaining:
            out_lines.append(f"{key}={remaining.pop(key)}")
        else:
            out_lines.append(raw)

    for key, value in remaining.items():
        out_lines.append(f"{key}={value}")

    text = "\n".join(out_lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")

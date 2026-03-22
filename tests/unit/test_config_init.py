from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.config_init import ensure_initial_config, required_api_keys


def test_required_api_keys_defaults() -> None:
    settings = TraceSettings()
    keys = required_api_keys(settings)
    assert "GROQ_API_KEY" in keys
    assert "TAVILY_API_KEY" in keys


def test_ensure_initial_config_uses_existing_env_file(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("GROQ_API_KEY=g\nTAVILY_API_KEY=t\n", encoding="utf-8")

    prompts = []
    outputs = []

    ensure_initial_config(
        TraceSettings(workspace_root=tmp_path),
        secret_prompt_fn=lambda prompt: prompts.append(prompt) or "",
        output_fn=outputs.append,
    )

    assert prompts == []
    assert any("using env file" in out for out in outputs)


def test_ensure_initial_config_prompts_and_writes_missing_keys(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("GROQ_API_KEY=existing\n", encoding="utf-8")

    prompts = []
    outputs = []

    ensure_initial_config(
        TraceSettings(workspace_root=tmp_path),
        secret_prompt_fn=lambda prompt: prompts.append(prompt) or "new-tavily",
        output_fn=outputs.append,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=existing" in text
    assert "TAVILY_API_KEY=new-tavily" in text
    assert any("missing API keys" in line for line in outputs)


def test_ensure_initial_config_honors_env_var_without_prompt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "from-env")

    prompts = []
    ensure_initial_config(
        TraceSettings(workspace_root=tmp_path),
        secret_prompt_fn=lambda prompt: prompts.append(prompt) or "",
        output_fn=lambda _text: None,
    )

    assert not any("TAVILY_API_KEY" in p for p in prompts)

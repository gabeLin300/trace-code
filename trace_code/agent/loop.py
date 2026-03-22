from __future__ import annotations
from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.llm.base import ProviderError, ProviderSelectionError
from trace_code.llm.manager import LLMManager
from trace_code.mcp.manager import MCPManager
from trace_code.rag.augment import build_augmented_prompt
from trace_code.tools.executor import ToolExecutionError, execute_tool_from_prompt


def run_turn(
    user_input: str,
    wants_tool: bool,
    settings: TraceSettings | None = None,
    provider_override: str | None = None,
    mcp_manager: MCPManager | None = None,
) -> dict:
    settings = settings or TraceSettings()

    if wants_tool:
        try:
            tool_result = execute_tool_from_prompt(
                user_input=user_input,
                workspace_root=Path(settings.workspace_root),
                settings=settings,
                mcp_manager=mcp_manager,
            )
            return {
                "status": "tool_called" if tool_result.get("status") == "ok" else tool_result.get("status", "tool_called"),
                "tool": tool_result["tool_name"],
                "tool_status": tool_result.get("status", "ok"),
                "response": tool_result["output"],
            }
        except ToolExecutionError as exc:
            return {
                "status": "error",
                "response": f"Tool error: {exc}",
            }

    manager = LLMManager(settings)
    prompt = build_augmented_prompt(
        user_input,
        settings=settings,
        workspace_root=Path(settings.workspace_root),
        mcp_manager=mcp_manager,
    )
    try:
        response = manager.generate(prompt=prompt, provider_override=provider_override)
    except (ProviderError, ProviderSelectionError) as exc:
        return {
            "status": "error",
            "response": f"LLM error: {exc}",
        }

    return {
        "status": "answered",
        "provider": response.provider,
        "model": response.model,
        "response": response.content,
    }

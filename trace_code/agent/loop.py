from __future__ import annotations
from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.llm.base import ProviderError, ProviderSelectionError
from trace_code.llm.manager import LLMManager
from trace_code.mcp.manager import MCPManager
from trace_code.rag.augment import build_augmented_prompt
from trace_code.tools.executor import ToolExecutionError, execute_tool_from_prompt, prompt_requests_tool


def run_agentic_task(
    user_input: str,
    *,
    settings: TraceSettings | None = None,
    provider_override: str | None = None,
    mcp_manager: MCPManager | None = None,
    max_steps: int = 4,
) -> dict:
    """
    Run a bounded autonomous task loop.

    Behavior:
    - If input is not tool-oriented, answer directly with the LLM.
    - If input is tool-oriented, execute the tool, then ask the LLM whether to:
      - continue with another tool command, or
      - return a final answer.
    """
    settings = settings or TraceSettings()
    manager = LLMManager(settings)

    steps: list[dict] = []
    tools: list[dict] = []
    current_tool_command = ""
    final_response = ""

    if prompt_requests_tool(user_input):
        current_tool_command = user_input
    else:
        initial_decision = _decide_initial_action(
            manager=manager,
            user_input=user_input,
            settings=settings,
            provider_override=provider_override,
            mcp_manager=mcp_manager,
        )
        steps.append({"step": 0, "kind": "initial_decision", **initial_decision})
        if initial_decision["action"] == "final":
            return {
                "status": "answered",
                "response": initial_decision["payload"],
                "steps": steps,
                "tools": [],
            }
        current_tool_command = initial_decision["payload"]

    for step_idx in range(1, max_steps + 1):
        tool_result = _run_tool_step(
            user_input=current_tool_command,
            settings=settings,
            mcp_manager=mcp_manager,
        )
        step = {"step": step_idx, "kind": "tool", **tool_result}
        steps.append(step)

        tool_name = step.get("tool")
        if tool_name:
            tools.append(
                {
                    "step": step_idx,
                    "tool_name": tool_name,
                    "status": step.get("status", "ok"),
                    "output": step.get("response", ""),
                }
            )

        status = step.get("status")
        if status in {"error", "blocked", "requires_confirmation"}:
            return {
                "status": status,
                "response": step.get("response", ""),
                "steps": steps,
                "tools": tools,
                "tool": step.get("tool"),
                "tool_status": step.get("tool_status"),
            }

        decision = _decide_next_action(
            manager=manager,
            original_user_input=user_input,
            latest_tool_name=str(step.get("tool", "")),
            latest_tool_output=str(step.get("response", "")),
            settings=settings,
            provider_override=provider_override,
            mcp_manager=mcp_manager,
        )
        steps.append({"step": step_idx, "kind": "decision", **decision})

        if decision["action"] == "tool":
            current_tool_command = decision["payload"]
            continue

        final_response = decision["payload"]
        return {
            "status": "answered_with_tools",
            "response": final_response,
            "steps": steps,
            "tools": tools,
            "tool": tools[-1]["tool_name"] if tools else None,
            "tool_status": tools[-1]["status"] if tools else None,
        }

    if not final_response and steps:
        final_response = str(steps[-1].get("response", "")).strip()
    if not final_response:
        final_response = "Completed available tool steps."

    return {
        "status": "step_limit_reached",
        "response": final_response,
        "steps": steps,
        "tools": tools,
        "tool": tools[-1]["tool_name"] if tools else None,
        "tool_status": tools[-1]["status"] if tools else None,
    }


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


def _run_tool_step(
    *,
    user_input: str,
    settings: TraceSettings,
    mcp_manager: MCPManager | None,
) -> dict:
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
        return {"status": "error", "response": f"Tool error: {exc}"}


def _decide_next_action(
    *,
    manager: LLMManager,
    original_user_input: str,
    latest_tool_name: str,
    latest_tool_output: str,
    settings: TraceSettings,
    provider_override: str | None,
    mcp_manager: MCPManager | None,
) -> dict[str, str]:
    decision_prompt = (
        "You are deciding the next step for an autonomous coding assistant.\n"
        "Given the user goal and latest tool result, return exactly one line:\n"
        "TOOL: <next tool command>\n"
        "or\n"
        "FINAL: <final user-facing answer>\n\n"
        f"User goal:\n{original_user_input}\n\n"
        f"Latest tool:\n{latest_tool_name}\n\n"
        f"Latest tool output:\n{latest_tool_output}\n"
    )
    prompt = build_augmented_prompt(
        decision_prompt,
        settings=settings,
        workspace_root=Path(settings.workspace_root),
        mcp_manager=mcp_manager,
    )
    try:
        response = manager.generate(prompt=prompt, provider_override=provider_override)
        text = response.content.strip()
    except (ProviderError, ProviderSelectionError):
        return {"action": "final", "payload": latest_tool_output}

    if text.lower().startswith("tool:"):
        payload = text.split(":", 1)[1].strip()
        if payload:
            return {"action": "tool", "payload": payload}
    if text.lower().startswith("final:"):
        payload = text.split(":", 1)[1].strip()
        if payload:
            return {"action": "final", "payload": payload}

    # Fall back to final response if the model does not follow the strict output format.
    return {"action": "final", "payload": text or latest_tool_output}


def _decide_initial_action(
    *,
    manager: LLMManager,
    user_input: str,
    settings: TraceSettings,
    provider_override: str | None,
    mcp_manager: MCPManager | None,
) -> dict[str, str]:
    prompt_text = (
        "You are deciding the first action for an autonomous coding assistant.\n"
        "Return exactly one line in one of these forms:\n"
        "TOOL: <tool command>\n"
        "FINAL: <direct answer>\n\n"
        "When the user asks for filesystem actions, web search, shell commands, or local docs retrieval, prefer TOOL.\n"
        "Tool command examples:\n"
        "- list files\n"
        "- read file README.md\n"
        "- search langchain docs for retrievers\n"
        "- search web for latest langchain release\n"
        "- run command git status\n\n"
        f"User request:\n{user_input}\n"
    )
    prompt = build_augmented_prompt(
        prompt_text,
        settings=settings,
        workspace_root=Path(settings.workspace_root),
        mcp_manager=mcp_manager,
    )
    try:
        response = manager.generate(prompt=prompt, provider_override=provider_override)
        text = response.content.strip()
    except (ProviderError, ProviderSelectionError):
        # Fall back to direct answer behavior when model planning step cannot run.
        direct_prompt = build_augmented_prompt(
            user_input,
            settings=settings,
            workspace_root=Path(settings.workspace_root),
            mcp_manager=mcp_manager,
        )
        try:
            direct = manager.generate(prompt=direct_prompt, provider_override=provider_override)
            return {"action": "final", "payload": direct.content}
        except (ProviderError, ProviderSelectionError) as exc:
            return {"action": "final", "payload": f"LLM error: {exc}"}

    if text.lower().startswith("tool:"):
        payload = text.split(":", 1)[1].strip()
        if payload:
            return {"action": "tool", "payload": payload}
    if text.lower().startswith("final:"):
        payload = text.split(":", 1)[1].strip()
        if payload:
            return {"action": "final", "payload": payload}

    # Default to a direct answer if tool-selection format is not followed.
    return {"action": "final", "payload": text}

from __future__ import annotations
import json
from pathlib import Path
import time
from typing import Callable

from trace_code.config import TraceSettings
from trace_code.llm.base import ProviderError, ProviderSelectionError
from trace_code.llm.manager import LLMManager
from trace_code.mcp.manager import MCPManager
from trace_code.rag.augment import build_augmented_prompt
from trace_code.tools.executor import (
    ToolExecutionError,
    execute_tool_call,
    execute_tool_from_prompt,
    normalize_tool_name,
    prompt_requests_tool,
    supported_tool_specs,
)
from trace_code.utils.timeout import call_with_timeout


def run_agentic_task(
    user_input: str,
    *,
    settings: TraceSettings | None = None,
    provider_override: str | None = None,
    mcp_manager: MCPManager | None = None,
    max_steps: int = 6,
    debug_fn: Callable[[str], None] | None = None,
) -> dict:
    """Run a bounded autonomous loop with explicit planner/executor/evaluator stages."""
    settings = settings or TraceSettings()
    manager = LLMManager(settings)

    steps: list[dict] = []
    tools: list[dict] = []
    action_history: list[str] = []
    output_signatures: list[str] = []
    latest_tool_name = ""
    latest_tool_output = ""

    for step_idx in range(1, max_steps + 1):
        _emit_debug(debug_fn, f"loop step {step_idx} start")
        _emit_debug(debug_fn, f"loop step {step_idx} planning start")
        decision = _plan_next_action(
            manager=manager,
            user_input=user_input,
            latest_tool_name=latest_tool_name,
            latest_tool_output=latest_tool_output,
            settings=settings,
            provider_override=provider_override,
            mcp_manager=mcp_manager,
            is_first_step=(step_idx == 1),
            debug_fn=debug_fn,
        )
        _emit_debug(debug_fn, f"loop step {step_idx} planning end action={decision.get('action')}")
        steps.append({"step": step_idx, "kind": "decision", **decision})
        if decision["action"] == "final":
            final_eval = _evaluate_final_completion(
                user_input=user_input,
                response=str(decision.get("payload", "")),
                used_tools=bool(tools),
            )
            steps.append({"step": step_idx, "kind": "evaluation", "phase": "final", **final_eval})
            if not final_eval["is_complete"] and step_idx < max_steps:
                recovery = _recover_from_incomplete_final(
                    manager=manager,
                    user_input=user_input,
                    partial_response=str(decision.get("payload", "")),
                    latest_tool_name=latest_tool_name,
                    latest_tool_output=latest_tool_output,
                    settings=settings,
                    provider_override=provider_override,
                    mcp_manager=mcp_manager,
                    unmet_requirements=list(final_eval.get("unmet_requirements", [])),
                    debug_fn=debug_fn,
                )
                if recovery["action"] == "tool":
                    decision = recovery
                    steps.append(
                        {
                            "step": step_idx,
                            "kind": "decision_override",
                            "reason": "final_response_incomplete",
                            "action": "tool",
                            "tool_name": recovery.get("tool_name", ""),
                            "arguments": recovery.get("arguments", {}),
                            "payload": recovery.get("payload", ""),
                        }
                    )
                else:
                    _emit_debug(debug_fn, f"loop step {step_idx} finalize done")
                    return _finalize_result(
                        status="answered" if not tools else "answered_with_tools",
                        response=decision["payload"],
                        steps=steps,
                        tools=tools,
                        stop_reason="done",
                        completion=final_eval,
                    )
            else:
                _emit_debug(debug_fn, f"loop step {step_idx} finalize done")
                return _finalize_result(
                    status="answered" if not tools else "answered_with_tools",
                    response=decision["payload"],
                    steps=steps,
                    tools=tools,
                    stop_reason="done",
                    completion=final_eval,
                )

        command = decision.get("payload", "")
        tool_name = decision.get("tool_name", "")
        arguments = decision.get("arguments", {})
        next_action_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}" if tool_name else str(command)
        guard = _evaluate_progress_guardrails(
            next_action_key=next_action_key,
            action_history=action_history,
            output_signatures=output_signatures,
        )
        if guard is not None:
            steps.append({"step": step_idx, "kind": "guardrail", **guard})
            _emit_debug(debug_fn, f"loop step {step_idx} guardrail stop={guard['stop_reason']}")
            return _finalize_result(
                status=guard["status"],
                response=guard["response"],
                steps=steps,
                tools=tools,
                stop_reason=guard["stop_reason"],
                completion={
                    "is_complete": False,
                    "confidence": "low",
                    "unmet_requirements": ["loop_guardrail_triggered"],
                    "reason": guard["stop_reason"],
                },
            )

        action_history.append(next_action_key)
        _emit_debug(debug_fn, f"loop step {step_idx} execute start tool={tool_name or command}")
        tool_result = _execute_action(
            command=command,
            tool_name=tool_name,
            arguments=arguments,
            settings=settings,
            mcp_manager=mcp_manager,
            debug_fn=debug_fn,
        )
        _emit_debug(debug_fn, f"loop step {step_idx} execute end status={tool_result.get('status')}")
        steps.append({"step": step_idx, "kind": "tool", **tool_result})

        if tool_result.get("tool"):
            tools.append(
                {
                    "step": step_idx,
                    "tool_name": tool_result.get("tool", "unknown"),
                    "status": tool_result.get("status", "unknown"),
                    "output": tool_result.get("response", ""),
                    "arguments": tool_result.get("arguments", {}),
                    "confirmation_required": tool_result.get("confirmation_required", False),
                    "elapsed_ms": tool_result.get("elapsed_ms", 0),
                }
            )
            tool_eval = _evaluate_tool_progress(
                user_input=user_input,
                tool_name=str(tool_result.get("tool", "")),
                tool_output=str(tool_result.get("response", "")),
            )
            steps.append({"step": step_idx, "kind": "evaluation", "phase": "tool", **tool_eval})

        if tool_result.get("status") in {"error", "blocked", "requires_confirmation"}:
            _emit_debug(debug_fn, f"loop step {step_idx} stop_reason={tool_result.get('status')}")
            if tool_result.get("status") == "error" and latest_tool_output:
                partial = (
                    f"{latest_tool_output}\n\n"
                    f"Note: a follow-up tool call failed, so I returned the best available result. "
                    f"{tool_result.get('response', '')}"
                )
                return _finalize_result(
                    status="answered_with_tools",
                    response=partial,
                    steps=steps,
                    tools=tools,
                    stop_reason="partial_error",
                    completion={
                        "is_complete": False,
                        "confidence": "medium",
                        "unmet_requirements": ["follow_up_tool_failed"],
                        "reason": "partial_error",
                    },
                )
            return _finalize_result(
                status=str(tool_result.get("status", "error")),
                response=str(tool_result.get("response", "")),
                steps=steps,
                tools=tools,
                stop_reason="blocked" if tool_result.get("status") in {"blocked", "requires_confirmation"} else "error",
                completion={
                    "is_complete": False,
                    "confidence": "low",
                    "unmet_requirements": ["tool_execution_failed_or_blocked"],
                    "reason": str(tool_result.get("status", "error")),
                },
            )

        latest_tool_name = str(tool_result.get("tool", ""))
        latest_tool_output = str(tool_result.get("response", ""))
        output_signatures.append(_output_signature(latest_tool_name, latest_tool_output))
        _emit_debug(debug_fn, f"loop step {step_idx} end")

    _emit_debug(debug_fn, "loop stop_reason=step_limit")
    return _finalize_result(
        status="step_limit_reached",
        response=latest_tool_output or "Stopped due to step limit before final answer.",
        steps=steps,
        tools=tools,
        stop_reason="step_limit",
        completion={
            "is_complete": False,
            "confidence": "low",
            "unmet_requirements": ["step_limit_reached"],
            "reason": "step_limit",
        },
    )


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


def _execute_action(
    *,
    command: str,
    tool_name: str,
    arguments: dict,
    settings: TraceSettings,
    mcp_manager: MCPManager | None,
    debug_fn: Callable[[str], None] | None = None,
) -> dict:
    try:
        started = time.monotonic()
        if tool_name:
            _assert_tool_executable(tool_name=tool_name, mcp_manager=mcp_manager)
            ok, value, err = call_with_timeout(
                lambda: execute_tool_call(
                    tool_name=tool_name,
                    arguments=arguments,
                    workspace_root=Path(settings.workspace_root),
                    settings=settings,
                    mcp_manager=mcp_manager,
                ),
                timeout_s=30.0,
            )
            if not ok:
                raise ToolExecutionError(f"tool execution timeout/error: {err}")
            tool_result = value
        else:
            ok, value, err = call_with_timeout(
                lambda: execute_tool_from_prompt(
                    user_input=command,
                    workspace_root=Path(settings.workspace_root),
                    settings=settings,
                    mcp_manager=mcp_manager,
                ),
                timeout_s=30.0,
            )
            if not ok:
                raise ToolExecutionError(f"tool execution timeout/error: {err}")
            tool_result = value
        return {
            "status": "tool_called" if tool_result.get("status") == "ok" else tool_result.get("status", "tool_called"),
            "tool": tool_result["tool_name"],
            "tool_status": tool_result.get("status", "ok"),
            "response": tool_result["output"],
            "arguments": tool_result.get("arguments", arguments),
            "confirmation_required": bool(tool_result.get("confirmation_required", False)),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    except ToolExecutionError as exc:
        _emit_debug(debug_fn, f"execute error: {exc}")
        return {"status": "error", "response": f"Tool error: {exc}"}


def _plan_next_action(
    *,
    manager: LLMManager,
    user_input: str,
    latest_tool_name: str,
    latest_tool_output: str,
    settings: TraceSettings,
    provider_override: str | None,
    mcp_manager: MCPManager | None,
    is_first_step: bool,
    debug_fn: Callable[[str], None] | None = None,
) -> dict[str, str]:
    stage = "first" if is_first_step else "next"
    available_tools = _available_tools_for_prompt(mcp_manager)
    decision_prompt = _decision_prompt(
        user_input=user_input,
        latest_tool_name=latest_tool_name,
        latest_tool_output=latest_tool_output,
        stage=stage,
        available_tools=available_tools,
    )
    prompt = build_augmented_prompt(
        decision_prompt,
        settings=settings,
        workspace_root=Path(settings.workspace_root),
        mcp_manager=mcp_manager,
    )
    try:
        _emit_debug(debug_fn, "provider/model invocation start")
        ok, response, err = call_with_timeout(
            lambda: manager.generate(prompt=prompt, provider_override=provider_override),
            timeout_s=45.0,
        )
        _emit_debug(debug_fn, "provider/model invocation end")
        if not ok:
            raise ProviderError(f"model invocation timeout/error: {err}")
        text = response.content.strip()
    except (ProviderError, ProviderSelectionError) as exc:
        if is_first_step:
            if prompt_requests_tool(user_input):
                # If user explicitly requested a tool command, preserve usability.
                return {"action": "tool", "payload": user_input, "tool_name": "", "arguments": {}}
            # Try a direct response as graceful fallback when the planner step cannot run.
            direct_prompt = build_augmented_prompt(
                user_input,
                settings=settings,
                workspace_root=Path(settings.workspace_root),
                mcp_manager=mcp_manager,
            )
            try:
                ok, direct, err = call_with_timeout(
                    lambda: manager.generate(prompt=direct_prompt, provider_override=provider_override),
                    timeout_s=45.0,
                )
                if not ok:
                    raise ProviderError(f"model invocation timeout/error: {err}")
                return {"action": "final", "payload": direct.content}
            except (ProviderError, ProviderSelectionError) as inner_exc:
                return {"action": "final", "payload": f"LLM error: {inner_exc}"}
        return {"action": "final", "payload": latest_tool_output or f"LLM error: {exc}"}

    decision = _parse_decision_response(text=text, fallback=latest_tool_output or text)
    if _needs_decision_repair(raw_text=text, decision=decision):
        repaired = _repair_decision_response(
            manager=manager,
            raw_text=text,
            fallback=latest_tool_output or text,
            settings=settings,
            provider_override=provider_override,
            mcp_manager=mcp_manager,
            debug_fn=debug_fn,
        )
        decision = repaired
    if is_first_step and prompt_requests_tool(user_input) and decision["action"] == "final":
        return {"action": "tool", "payload": user_input, "tool_name": "", "arguments": {}}
    return decision


def _decision_prompt(*, user_input: str, latest_tool_name: str, latest_tool_output: str, stage: str, available_tools: str) -> str:
    return (
        "You are deciding the action for an autonomous coding assistant.\n"
        "Return ONLY a single JSON object with one of these shapes:\n"
        '{"action":"tool","tool":"<tool_name>","arguments":{...}}\n'
        '{"action":"final","response":"<final user-facing answer>"}\n'
        "Do not include markdown fences or prose.\n"
        "If you need tools, choose only from the available tool list below.\n\n"
        "When using a dynamically discovered MCP tool, call tool='mcp.call' with:\n"
        '{"server":"<server_name>","tool":"<mcp_tool_name>","arguments":{...}}\n\n'
        f"Available tools:\n{available_tools}\n\n"
        f"Stage: {stage}\n"
        f"User goal:\n{user_input}\n\n"
        f"Latest tool:\n{latest_tool_name}\n\n"
        f"Latest tool output:\n{latest_tool_output}\n"
    )


def _parse_decision_response(*, text: str, fallback: str) -> dict[str, str]:
    stripped = text.strip()
    parsed = _parse_json_payload(stripped)
    if isinstance(parsed, dict):
        action = str(parsed.get("action", "")).strip().lower()
        if action == "tool":
            tool_name = str(parsed.get("tool", "") or parsed.get("tool_name", "")).strip()
            arguments = parsed.get("arguments", {})
            if isinstance(arguments, str):
                parsed_arguments = _parse_json_payload(arguments)
                if isinstance(parsed_arguments, dict):
                    arguments = parsed_arguments
            if isinstance(arguments, dict):
                if tool_name and not _is_supported_tool_name(tool_name):
                    return {
                        "action": "final",
                        "payload": f"Requested unsupported tool '{tool_name}'. Available tools were provided in prompt.",
                        "tool_name": "",
                        "arguments": {},
                    }
                return {
                    "action": "tool",
                    "payload": "",
                    "tool_name": tool_name,
                    "arguments": arguments,
                }
        if action == "final":
            response = str(parsed.get("response", "") or parsed.get("final", "")).strip()
            return {"action": "final", "payload": response or fallback, "tool_name": "", "arguments": {}}

    lowered = stripped.lower()
    if lowered.startswith("tool:"):
        payload = stripped.split(":", 1)[1].strip()
        if payload:
            if not prompt_requests_tool(payload):
                return {"action": "final", "payload": payload, "tool_name": "", "arguments": {}}
            return {"action": "tool", "payload": payload, "tool_name": "", "arguments": {}}
    if lowered.startswith("final:"):
        payload = stripped.split(":", 1)[1].strip()
        if payload:
            return {"action": "final", "payload": payload, "tool_name": "", "arguments": {}}
    return {"action": "final", "payload": stripped or fallback, "tool_name": "", "arguments": {}}


def _recover_from_incomplete_final(
    *,
    manager: LLMManager,
    user_input: str,
    partial_response: str,
    latest_tool_name: str,
    latest_tool_output: str,
    settings: TraceSettings,
    provider_override: str | None,
    mcp_manager: MCPManager | None,
    unmet_requirements: list[str],
    debug_fn: Callable[[str], None] | None = None,
) -> dict[str, str]:
    available_tools = _available_tools_for_prompt(mcp_manager)
    unmet = ", ".join(unmet_requirements) if unmet_requirements else "none"
    prompt = (
        "The previous FINAL answer is incomplete.\n"
        "Return ONLY JSON with one of:\n"
        '{"action":"tool","tool":"<tool_name>","arguments":{...}}\n'
        '{"action":"final","response":"<improved final answer>"}\n\n'
        "Prefer action=tool when additional evidence is needed.\n"
        "Choose tools only from this list:\n"
        f"{available_tools}\n\n"
        f"User goal:\n{user_input}\n\n"
        f"Previous incomplete answer:\n{partial_response}\n\n"
        f"Latest tool name:\n{latest_tool_name}\n\n"
        f"Latest tool output:\n{latest_tool_output}\n\n"
        f"Unmet requirements:\n{unmet}\n"
    )
    augmented = build_augmented_prompt(
        prompt,
        settings=settings,
        workspace_root=Path(settings.workspace_root),
        mcp_manager=mcp_manager,
    )
    try:
        _emit_debug(debug_fn, "recovery planner invocation start")
        ok, response, err = call_with_timeout(
            lambda: manager.generate(prompt=augmented, provider_override=provider_override),
            timeout_s=45.0,
        )
        _emit_debug(debug_fn, "recovery planner invocation end")
        if not ok:
            raise ProviderError(f"recovery planner timeout/error: {err}")
        repaired = _parse_decision_response(text=response.content.strip(), fallback=partial_response)
        if repaired["action"] == "tool":
            return repaired
        if repaired["action"] == "final":
            return repaired
    except Exception as exc:
        _emit_debug(debug_fn, f"recovery planner failed: {exc}")

    # Conservative fallback: only force a tool when the original task appears tool-oriented.
    if prompt_requests_tool(user_input):
        return {"action": "tool", "payload": user_input, "tool_name": "", "arguments": {}}
    return {"action": "final", "payload": partial_response, "tool_name": "", "arguments": {}}


def _evaluate_progress_guardrails(
    *,
    next_action_key: str,
    action_history: list[str],
    output_signatures: list[str],
) -> dict[str, str] | None:
    recent_actions = action_history[-2:]
    if len(recent_actions) == 2 and recent_actions[0] == recent_actions[1] == next_action_key:
        return {
            "status": "no_progress",
            "response": f"Stopping to avoid repeating the same tool action: {next_action_key}",
            "stop_reason": "repeated_tool",
        }

    if len(output_signatures) >= 2 and output_signatures[-1] == output_signatures[-2]:
        return {
            "status": "no_progress",
            "response": "Stopping because consecutive tool outputs are unchanged (no progress detected).",
            "stop_reason": "no_progress",
        }

    return None


def _output_signature(tool_name: str, output: str) -> str:
    # Cheap signature for loop progress checks.
    normalized = " ".join(output.split())[:220]
    return f"{tool_name}::{normalized}"


def _finalize_result(
    *,
    status: str,
    response: str,
    steps: list[dict],
    tools: list[dict],
    stop_reason: str,
    completion: dict | None = None,
) -> dict:
    if completion is None:
        completion = _default_completion(status=status, response=response)
    return {
        "status": status,
        "response": response,
        "steps": steps,
        "tools": tools,
        "tool": tools[-1]["tool_name"] if tools else None,
        "tool_status": tools[-1]["status"] if tools else None,
        "stop_reason": stop_reason,
        "completion": completion,
    }


def _available_tools_for_prompt(mcp_manager: MCPManager | None) -> str:
    dynamic = {}
    if mcp_manager is not None:
        try:
            dynamic = mcp_manager.available_tools()
        except Exception:
            dynamic = {}

    rows: list[str] = []
    for spec in supported_tool_specs():
        rows.append(f"- {spec['name']}: {spec['description']} args={json.dumps(spec['arguments'], ensure_ascii=True)}")
    if dynamic:
        rows.append(f"- dynamic_mcp_tools={json.dumps(dynamic, ensure_ascii=True)}")
    return "\n".join(rows)


def _parse_json_payload(text: str) -> dict | None:
    # Accept plain JSON or JSON wrapped in markdown code fences.
    candidates = [text]
    if "```" in text:
        inner = text
        inner = inner.replace("```json", "```").replace("```JSON", "```")
        parts = [p.strip() for p in inner.split("```") if p.strip()]
        candidates.extend(parts)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _needs_decision_repair(*, raw_text: str, decision: dict[str, str]) -> bool:
    if decision.get("action") == "tool":
        return False
    raw = raw_text.strip().lower()
    if not raw:
        return False
    if raw.startswith("{") or raw.startswith("tool:") or raw.startswith("final:"):
        return False
    # If the model ignored the structured contract and returned prose,
    # run a one-shot repair step to recover a valid action JSON.
    return True


def _repair_decision_response(
    *,
    manager: LLMManager,
    raw_text: str,
    fallback: str,
    settings: TraceSettings,
    provider_override: str | None,
    mcp_manager: MCPManager | None,
    debug_fn: Callable[[str], None] | None = None,
) -> dict[str, str]:
    repair_prompt = (
        "Rewrite the following planner output as a strict JSON action object.\n"
        "Return ONLY JSON in one shape:\n"
        '{"action":"tool","tool":"<tool_name>","arguments":{...}}\n'
        '{"action":"final","response":"<final user-facing answer>"}\n\n'
        "Original output:\n"
        f"{raw_text}\n"
    )
    augmented = build_augmented_prompt(
        repair_prompt,
        settings=settings,
        workspace_root=Path(settings.workspace_root),
        mcp_manager=mcp_manager,
    )
    try:
        _emit_debug(debug_fn, "decision repair invocation start")
        ok, response, err = call_with_timeout(
            lambda: manager.generate(prompt=augmented, provider_override=provider_override),
            timeout_s=25.0,
        )
        _emit_debug(debug_fn, "decision repair invocation end")
        if not ok:
            raise ProviderError(f"decision repair timeout/error: {err}")
        return _parse_decision_response(text=response.content.strip(), fallback=fallback)
    except Exception as exc:
        _emit_debug(debug_fn, f"decision repair failed: {exc}")
        return _parse_decision_response(text=raw_text, fallback=fallback)


def _is_supported_tool_name(tool_name: str) -> bool:
    names = {spec["name"] for spec in supported_tool_specs()}
    return normalize_tool_name(tool_name) in names


def _assert_tool_executable(*, tool_name: str, mcp_manager: MCPManager | None) -> None:
    if mcp_manager is None:
        return
    normalized = normalize_tool_name(tool_name)
    if normalized.startswith("fs."):
        server = "filesystem"
    elif normalized.startswith("knowledge."):
        server = "local_knowledge"
    elif normalized.startswith("web."):
        server = "web_search"
    else:
        return
    diag = mcp_manager.diagnostics().get(server)
    if diag is None:
        return
    if not diag.connected or not diag.executable:
        detail = diag.executable_detail or diag.startup_error or "server not executable"
        raise ToolExecutionError(f"MCP server '{server}' is unavailable: {detail}")


def _emit_debug(debug_fn: Callable[[str], None] | None, message: str) -> None:
    if debug_fn is not None:
        debug_fn(message)


def _evaluate_tool_progress(*, user_input: str, tool_name: str, tool_output: str) -> dict[str, object]:
    normalized = " ".join(tool_output.split())
    has_signal = bool(normalized and normalized.lower() not in {"(empty)", "no matches found."})
    confidence = "high" if has_signal else "low"
    unmet: list[str] = []
    if not has_signal:
        unmet.append("tool_returned_empty_or_low_signal_output")
    return {
        "is_complete": False,
        "confidence": confidence,
        "unmet_requirements": unmet,
        "reason": f"tool_observation:{tool_name}",
    }


def _evaluate_final_completion(*, user_input: str, response: str, used_tools: bool) -> dict[str, object]:
    text = response.strip()
    lowered = text.lower()
    blockers = (
        "i don't know",
        "cannot",
        "can't",
        "unable",
        "not sure",
        "insufficient",
    )
    unmet: list[str] = []
    if not text:
        unmet.append("empty_final_response")
    if any(b in lowered for b in blockers):
        unmet.append("final_response_indicates_incomplete_resolution")
    if prompt_requests_tool(user_input) and not used_tools:
        unmet.append("tool_oriented_goal_without_tool_use")

    is_complete = len(unmet) == 0
    if is_complete:
        confidence = "high" if len(text) >= 20 else "medium"
    else:
        confidence = "low" if "empty_final_response" in unmet else "medium"
    return {
        "is_complete": is_complete,
        "confidence": confidence,
        "unmet_requirements": unmet,
        "reason": "final_response_check",
    }


def _default_completion(*, status: str, response: str) -> dict[str, object]:
    if status in {"answered", "answered_with_tools"} and response.strip():
        return {"is_complete": True, "confidence": "medium", "unmet_requirements": [], "reason": "default_finalization"}
    return {
        "is_complete": False,
        "confidence": "low",
        "unmet_requirements": ["non_answer_terminal_state"],
        "reason": "default_finalization",
    }

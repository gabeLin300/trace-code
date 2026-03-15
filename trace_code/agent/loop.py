from __future__ import annotations


def run_turn(user_input: str, wants_tool: bool) -> dict:
    if wants_tool:
        return {
            "status": "tool_called",
            "tool": "mock_tool",
            "response": f"Executed tool for: {user_input}",
        }
    return {
        "status": "answered",
        "response": f"Answer for: {user_input}",
    }

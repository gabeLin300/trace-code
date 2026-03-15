import pytest

from trace_code.agent.loop import run_turn
from trace_code.mcp.router import route_tool


def test_agent_loop_branches() -> None:
    tool_path = run_turn("list files", wants_tool=True)
    answer_path = run_turn("explain code", wants_tool=False)

    assert tool_path["status"] == "tool_called"
    assert answer_path["status"] == "answered"


def test_mcp_router_namespaces() -> None:
    assert route_tool("fs.read") == "filesystem"
    assert route_tool("knowledge.search") == "local_knowledge"
    assert route_tool("web.search") == "web_search"


def test_mcp_router_rejects_unknown_namespace() -> None:
    with pytest.raises(ValueError):
        route_tool("unknown.action")

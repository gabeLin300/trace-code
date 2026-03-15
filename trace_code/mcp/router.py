from __future__ import annotations


def route_tool(tool_name: str) -> str:
    if tool_name.startswith("fs."):
        return "filesystem"
    if tool_name.startswith("knowledge."):
        return "local_knowledge"
    if tool_name.startswith("web."):
        return "web_search"
    raise ValueError(f"Unknown tool namespace: {tool_name}")

from trace_code.config import MCPSettings


def test_python_commands_resolve_to_current_interpreter() -> None:
    s = MCPSettings(
        local_knowledge_server_command="python -m trace_code.mcp.local_knowledge_server",
        web_search_server_command="python -m trace_code.mcp.web_search_server --no-prompt",
    )
    local_cmd = s.local_knowledge_server_argv()
    web_cmd = s.web_search_server_argv()
    assert local_cmd[0].lower() != "python"
    assert web_cmd[0].lower() != "python"


def test_filesystem_command_keeps_package_name() -> None:
    s = MCPSettings(filesystem_server_command="npx -y @modelcontextprotocol/server-filesystem")
    cmd = s.filesystem_server_argv()
    assert "@modelcontextprotocol/server-filesystem" in cmd

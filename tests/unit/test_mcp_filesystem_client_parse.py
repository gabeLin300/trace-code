import pytest

from trace_code.mcp.filesystem_client import MCPClientError, _tool_result_text


def test_tool_result_text_from_content() -> None:
    result = {"content": [{"type": "text", "text": "hello"}]}
    assert _tool_result_text(result) == "hello"


def test_tool_result_text_from_structured_content() -> None:
    result = {"structuredContent": {"a": 1}}
    text = _tool_result_text(result)
    assert '"a": 1' in text


def test_tool_result_text_raises_without_content() -> None:
    with pytest.raises(MCPClientError):
        _tool_result_text({})

from trace_code.cli.app import start_cli
from trace_code.config import TraceSettings


def test_startup_shows_banner_by_default(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    result = start_cli(settings)
    assert "_____" in result["banner"]
    assert result["resumed"] is False


def test_startup_respects_no_banner_flag(tmp_path) -> None:
    settings = TraceSettings(workspace_root=tmp_path)
    result = start_cli(settings, no_banner=True)
    assert result["banner"] == ""

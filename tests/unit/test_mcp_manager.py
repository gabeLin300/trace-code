from pathlib import Path

from trace_code.config import TraceSettings
from trace_code.mcp import manager as m


class _AliveProcess:
    def poll(self):
        return None


class _DeadProcess:
    def poll(self):
        return 1


class _BaseFakeClient:
    def __init__(self):
        self.process = None
        self.closed = False
        self.fail_once = False

    def start(self):
        self.process = _AliveProcess()

    def close(self):
        self.closed = True
        self.process = None


class _FakeFilesystemClient(_BaseFakeClient):
    def __init__(self, command, workspace_root):
        super().__init__()

    def list_directory(self, directory):
        if self.fail_once:
            self.fail_once = False
            raise m.MCPClientError("boom")
        return "a.py"

    def read_file(self, path):
        return "content"


class _FakeLocalKnowledgeClient(_BaseFakeClient):
    def __init__(self, command):
        super().__init__()

    def ingest_langchain_docs(self, seed_url, max_pages, collection):
        return {"seed_url": seed_url, "pages_indexed": 1, "chunks_indexed": 2, "collection": collection}

    def search_langchain_docs(self, query, top_k, collection):
        return {"results": [{"text": "hello", "metadata": {"source_url": "u"}}]}


class _FakeWebClient(_BaseFakeClient):
    def __init__(self, command):
        super().__init__()

    def search(self, query, max_results, search_depth):
        return {"answer": "ok", "results": []}


def test_manager_start_health_and_close(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "FilesystemMCPClient", _FakeFilesystemClient)
    monkeypatch.setattr(m, "LocalKnowledgeMCPClient", _FakeLocalKnowledgeClient)
    monkeypatch.setattr(m, "WebSearchMCPClient", _FakeWebClient)

    mgr = m.MCPManager(settings=TraceSettings(workspace_root=tmp_path), workspace_root=tmp_path)
    mgr.start()

    health = mgr.health()
    assert health.filesystem is True
    assert health.local_knowledge is True
    assert health.web_search is True

    mgr.close()
    health2 = mgr.health()
    assert health2.filesystem is False
    assert health2.local_knowledge is False
    assert health2.web_search is False


def test_manager_restarts_filesystem_client_on_failure(monkeypatch, tmp_path: Path) -> None:
    created = []

    class _FactoryClient(_FakeFilesystemClient):
        def __init__(self, command, workspace_root):
            super().__init__(command, workspace_root)
            created.append(self)

    monkeypatch.setattr(m, "FilesystemMCPClient", _FactoryClient)
    monkeypatch.setattr(m, "LocalKnowledgeMCPClient", _FakeLocalKnowledgeClient)
    monkeypatch.setattr(m, "WebSearchMCPClient", _FakeWebClient)

    mgr = m.MCPManager(settings=TraceSettings(workspace_root=tmp_path), workspace_root=tmp_path)
    mgr.start()

    created[0].fail_once = True
    out = mgr.list_files(tmp_path)

    assert out == "a.py"
    assert len(created) >= 2

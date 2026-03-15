from trace_code.sessions.store import SessionRecord, SessionStore


def test_session_save_and_load_roundtrip(tmp_path) -> None:
    store = SessionStore(tmp_path)
    record = SessionRecord(session_id="abc")
    record.chat_history.append({"role": "user", "content": "hi"})

    path = store.save(record)
    loaded = store.load("abc")

    assert path.exists()
    assert loaded.session_id == "abc"
    assert loaded.chat_history[0]["content"] == "hi"

from elk_lead_agent.state import StateStore


def test_state_roundtrip(tmp_path):
    path = tmp_path / "seen.json"
    store = StateStore(path=path)
    assert not store.is_seen("abc")
    store.mark_seen(["abc", "def"])
    store.save()

    reopened = StateStore(path=path)
    assert reopened.is_seen("abc")
    assert reopened.is_seen("def")
    assert not reopened.is_seen("xyz")


def test_disabled_state_never_persists(tmp_path):
    path = tmp_path / "seen.json"
    store = StateStore(path=path, enabled=False)
    store.mark_seen(["abc"])
    store.save()
    assert not path.exists()
    assert not store.is_seen("abc")

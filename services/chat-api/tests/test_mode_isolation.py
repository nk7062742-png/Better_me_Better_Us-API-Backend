from app.core.qdrant_db import KB_COLLECTIONS, MEMORY_COLLECTIONS
from app.services import rag


def _setup_common_mocks(monkeypatch):
    monkeypatch.setattr(rag, "get_embedding", lambda _: [0.01, 0.02, 0.03])
    monkeypatch.setattr(rag, "ask_llm", lambda *_, **__: "safe reply")
    monkeypatch.setattr(rag, "evaluate_input", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(rag, "evaluate_output", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(rag, "_save_memory", lambda *_, **__: None)
    monkeypatch.setattr(rag, "append_chat_turn", lambda *_, **__: None)
    monkeypatch.setattr(rag, "load_chat_turns", lambda *_, **__: [])
    monkeypatch.setattr(rag, "enforce_chat_budget", lambda *_, **__: None)
    rag.SESSION_HISTORY.clear()
    rag.SESSION_OWNERS.clear()


def test_mode_queries_use_only_mode_specific_collections(monkeypatch):
    _setup_common_mocks(monkeypatch)
    calls = []

    def fake_search(collection, vector, limit, flt=None):
        calls.append(collection)
        return ["context"] if collection in KB_COLLECTIONS.values() else ["memory"]

    monkeypatch.setattr(rag, "_search", fake_search)

    rag.run_rag(
        mode="coaching",
        user_id="u1",
        session_id="sess-1",
        query="I need clarity for this week",
    )

    assert KB_COLLECTIONS["coaching"] in calls
    assert MEMORY_COLLECTIONS["coaching"] in calls
    assert KB_COLLECTIONS["personal_growth"] not in calls
    assert MEMORY_COLLECTIONS["personal_growth"] not in calls
    assert KB_COLLECTIONS["relationship_private"] not in calls
    assert MEMORY_COLLECTIONS["relationship_private"] not in calls


def test_memory_filter_is_user_scoped_not_session_scoped(monkeypatch):
    _setup_common_mocks(monkeypatch)
    memory_filters = []

    def fake_search(collection, vector, limit, flt=None):
        if collection == MEMORY_COLLECTIONS["personal_growth"]:
            memory_filters.append(flt)
        return []

    monkeypatch.setattr(rag, "_search", fake_search)

    rag.run_rag(
        mode="personal_growth",
        user_id="u1",
        session_id="sess-xyz",
        query="Help me reflect on my stress",
    )

    assert memory_filters, "Expected at least one memory query"
    keys = [condition.key for condition in memory_filters[0].must]
    assert "user_id" in keys
    assert "session_id" not in keys

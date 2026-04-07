from app.services import rag


def test_run_rag_calls_budget_guard(monkeypatch):
    called = {"value": False}

    def fake_enforce_chat_budget(*, user_id, user_text):
        called["value"] = True
        assert user_id == "u1"
        assert user_text == "hello"

    monkeypatch.setattr(rag, "enforce_chat_budget", fake_enforce_chat_budget)
    monkeypatch.setattr(rag, "get_embedding", lambda _: [0.01, 0.02, 0.03])
    monkeypatch.setattr(rag, "ask_llm", lambda *_, **__: "safe reply")
    monkeypatch.setattr(rag, "evaluate_input", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(rag, "evaluate_output", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(rag, "_save_memory", lambda *_, **__: None)
    monkeypatch.setattr(rag, "append_chat_turn", lambda *_, **__: None)
    monkeypatch.setattr(rag, "load_chat_turns", lambda *_, **__: [])
    monkeypatch.setattr(rag, "_search", lambda *_, **__: [])
    rag.SESSION_OWNERS.clear()

    rag.run_rag(
        mode="personal_growth",
        user_id="u1",
        session_id="sess-1",
        query="hello",
    )

    assert called["value"] is True

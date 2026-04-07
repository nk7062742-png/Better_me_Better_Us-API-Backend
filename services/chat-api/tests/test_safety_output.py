from app.core import safety


def test_evaluate_output_does_not_hard_block_when_moderation_unavailable(monkeypatch):
    monkeypatch.setattr(
        safety,
        "_moderate_openai",
        lambda _text: (False, "Service unavailable", {"error": "moderation_unavailable"}),
    )

    safe, _msg = safety.evaluate_output("This is a harmless coaching reply.", user_id="u1")

    assert safe is True


def test_evaluate_output_blocks_when_moderation_flags_content(monkeypatch):
    monkeypatch.setattr(
        safety,
        "_moderate_openai",
        lambda _text: (False, "unsafe", {"flagged": True, "categories": {"violence": True}}),
    )

    safe, msg = safety.evaluate_output("unsafe text", user_id="u1")

    assert safe is False
    assert "I can’t provide that" in msg

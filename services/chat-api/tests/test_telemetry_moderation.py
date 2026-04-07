from app.core import telemetry


def test_log_moderation_normalizes_user_id_from_userId(monkeypatch):
    captured = {}

    monkeypatch.setattr(telemetry, "log_request", lambda *_args, **_kwargs: None)

    def fake_sync(event):
        captured["event"] = event

    monkeypatch.setattr(telemetry, "sync_moderation_event", fake_sync)

    telemetry.log_moderation({"flagged": True, "userId": "u-123", "channel": "input"})

    assert captured["event"]["user_id"] == "u-123"
    assert captured["event"]["userId"] == "u-123"


def test_log_moderation_falls_back_to_unknown_for_blank_user(monkeypatch):
    captured = {}
    monkeypatch.setattr(telemetry, "log_request", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(telemetry, "sync_moderation_event", lambda event: captured.setdefault("event", event))

    telemetry.log_moderation({"flagged": True, "user_id": "   ", "channel": "input"})

    assert captured["event"]["user_id"] == "unknown"
    assert captured["event"]["userId"] == "unknown"

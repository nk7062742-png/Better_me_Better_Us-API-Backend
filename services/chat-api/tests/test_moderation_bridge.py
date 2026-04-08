from app.core import firestore_bridge


def test_sync_moderation_event_uses_event_timestamp_and_user(monkeypatch):
    captured = {}

    def fake_request(method, path, body=None, query=None):
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body
        return {}

    monkeypatch.setattr(firestore_bridge, "_request_json", fake_request)

    firestore_bridge.sync_moderation_event(
        {
            "flagged": True,
            "channel": "input",
            "reason": "moderation_flag",
            "user_id": "user-123",
            "input_preview": "preview text",
            "timestamp": "2026-04-07T12:34:56+00:00",
        }
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "flagged_responses"
    fields = captured["body"]["fields"]
    assert fields["userId"]["stringValue"] == "user-123"
    assert fields["response"]["stringValue"] == "preview text"
    assert fields["flaggedAt"]["timestampValue"] == "2026-04-07T12:34:56Z"


def test_sync_moderation_event_skips_unflagged(monkeypatch):
    called = {"value": False}

    def fake_request(method, path, body=None, query=None):
        called["value"] = True
        return {}

    monkeypatch.setattr(firestore_bridge, "_request_json", fake_request)
    firestore_bridge.sync_moderation_event({"flagged": False, "user_id": "u1"})

    assert called["value"] is False


def test_sync_moderation_event_skips_missing_user_id(monkeypatch):
    called = {"value": False}

    def fake_request(method, path, body=None, query=None):
        called["value"] = True
        return {}

    monkeypatch.setattr(firestore_bridge, "_request_json", fake_request)
    firestore_bridge.sync_moderation_event({"flagged": True, "user_id": "unknown"})

    assert called["value"] is False


def test_sync_moderation_event_prefers_non_placeholder_user_id(monkeypatch):
    captured = {}

    def fake_request(method, path, body=None, query=None):
        captured["body"] = body
        return {}

    monkeypatch.setattr(firestore_bridge, "_request_json", fake_request)
    firestore_bridge.sync_moderation_event(
        {
            "flagged": True,
            "channel": "input",
            "reason": "moderation_flag",
            "user_id": "unknown",
            "userId": "real-uid-77",
            "input_preview": "preview text",
        }
    )

    fields = captured["body"]["fields"]
    assert fields["userId"]["stringValue"] == "real-uid-77"


def test_sync_moderation_event_persists_moderation_unavailable_reason(monkeypatch):
    captured = {}

    def fake_request(method, path, body=None, query=None):
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body
        return {}

    monkeypatch.setattr(firestore_bridge, "_request_json", fake_request)
    firestore_bridge.sync_moderation_event(
        {
            "flagged": False,
            "reason": "moderation_unavailable",
            "channel": "input",
            "user_id": "user-789",
            "input_preview": "preview text",
        }
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "flagged_responses"
    fields = captured["body"]["fields"]
    assert fields["userId"]["stringValue"] == "user-789"
    assert fields["reason"]["stringValue"] == "moderation_unavailable"

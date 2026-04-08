from app.core.auth import _resolve_user_id_from_claims


def test_resolve_user_id_prefers_uid_over_placeholder_sub():
    claims = {
        "sub": "unknown",
        "uid": "real-firebase-uid-123",
    }

    assert _resolve_user_id_from_claims(claims) == "real-firebase-uid-123"


def test_resolve_user_id_uses_sub_when_uid_missing():
    claims = {"sub": "sub-user-456"}

    assert _resolve_user_id_from_claims(claims) == "sub-user-456"

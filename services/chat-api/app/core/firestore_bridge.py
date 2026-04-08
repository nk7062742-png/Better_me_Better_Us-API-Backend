import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
try:
    from app.core.request_context import get_current_user_id as get_context_user_id
except ModuleNotFoundError:  # pragma: no cover
    def get_context_user_id() -> Optional[str]:
        return None

import logging

logger = logging.getLogger(__name__)

FIRESTORE_SCOPE = ["https://www.googleapis.com/auth/datastore"]
FIRESTORE_PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID", "").strip()
FIRESTORE_ENABLED = os.getenv("FIRESTORE_SYNC_ENABLED", "true").lower() == "true"
GOOGLE_CREDENTIALS_JSON = (
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
)

_credentials = None
_resolved_project_id: Optional[str] = None
_firestore_runtime_disabled = False
_firestore_disable_reason_logged = False


def _normalize_user_id(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip()
    if normalized.lower() in {"", "unknown", "null", "none"}:
        return ""
    return normalized


def _firestore_configured() -> bool:
    return FIRESTORE_ENABLED and not _firestore_runtime_disabled


def _get_auth() -> tuple[Optional[str], Optional[str]]:
    global _credentials, _resolved_project_id, _firestore_runtime_disabled, _firestore_disable_reason_logged
    if not _firestore_configured():
        return None, None
    try:
        if _credentials is None:
            if GOOGLE_CREDENTIALS_JSON:
                info = json.loads(GOOGLE_CREDENTIALS_JSON)
                _credentials = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=FIRESTORE_SCOPE,
                )
                _resolved_project_id = FIRESTORE_PROJECT_ID or str(info.get("project_id") or "").strip()
            else:
                _credentials, detected_project = google.auth.default(scopes=FIRESTORE_SCOPE)
                _resolved_project_id = FIRESTORE_PROJECT_ID or detected_project
        if not _resolved_project_id:
            _firestore_runtime_disabled = True
            if not _firestore_disable_reason_logged:
                logger.warning(
                    "firestore_sync_disabled: missing project id. "
                    "Set FIRESTORE_PROJECT_ID and credentials env vars."
                )
                _firestore_disable_reason_logged = True
            return None, None
        if not _credentials.valid:
            _credentials.refresh(GoogleAuthRequest())
        return _credentials.token, _resolved_project_id
    except Exception as exc:
        _firestore_runtime_disabled = True
        if not _firestore_disable_reason_logged:
            logger.warning(
                "firestore_sync_disabled_after_auth_failure: %s. "
                "Set GOOGLE_APPLICATION_CREDENTIALS_JSON (or FIREBASE_SERVICE_ACCOUNT_JSON) "
                "and FIRESTORE_PROJECT_ID in deployment env.",
                exc,
            )
            _firestore_disable_reason_logged = True
        return None, None


def _to_firestore_value(value: Any) -> Dict[str, Any]:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, datetime):
        return {"timestampValue": value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
    return {"stringValue": str(value)}


def _from_firestore_value(value: Dict[str, Any]) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "integerValue" in value:
        return int(value["integerValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "booleanValue" in value:
        return bool(value["booleanValue"])
    if "timestampValue" in value:
        return value["timestampValue"]
    return None


def _request_json(method: str, path: str, body: Optional[Dict[str, Any]] = None, query: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    token, project_id = _get_auth()
    if not token or not project_id:
        return None

    qs = f"?{urlencode(query)}" if query else ""
    url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{path}{qs}"
    data = None if body is None else bytes(json.dumps(body), encoding="utf-8")
    req = Request(
        url=url,
        method=method,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=8) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except Exception as exc:
        logger.warning("firestore_request_failed %s %s: %s", method, path, exc)
        return None


def _session_doc_id(mode: str, user_id: str, session_id: str, relationship_id: Optional[str]) -> str:
    key = f"{mode}|{user_id}|{session_id}|{relationship_id or ''}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _usage_doc_id(user_id: str, day: str) -> str:
    key = f"{user_id}|{day}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _extract_fields(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not payload:
        return {}
    return payload.get("fields", {})


def _parse_event_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized).astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def sync_moderation_event(event: Dict[str, Any]) -> None:
    if not event.get("flagged"):
        return
    event_ts = _parse_event_timestamp(event.get("timestamp"))
    event_user_id = (
        _normalize_user_id(event.get("user_id"))
        or _normalize_user_id(event.get("userId"))
        or _normalize_user_id(event.get("auth_user_id"))
        or _normalize_user_id(event.get("authUserId"))
        or _normalize_user_id(get_context_user_id())
    )
    if not event_user_id:
        logger.warning("skip_moderation_event_missing_user_id")
        return
    doc = {
        "fields": {
            "userId": _to_firestore_value(event_user_id),
            "response": _to_firestore_value(event.get("input_preview") or event.get("output_preview") or ""),
            "reason": _to_firestore_value(event.get("reason") or "moderation_flag"),
            "channel": _to_firestore_value(event.get("channel") or "unknown"),
            "status": _to_firestore_value("pending"),
            "flaggedAt": _to_firestore_value(event_ts),
            "source": _to_firestore_value("backend_moderation"),
        }
    }
    _request_json("POST", "flagged_responses", body=doc)


def append_chat_turn(
    *,
    mode: str,
    user_id: str,
    session_id: str,
    relationship_id: Optional[str],
    role: str,
    content: str,
) -> None:
    doc_id = _session_doc_id(mode, user_id, session_id, relationship_id)
    now = datetime.now(timezone.utc)
    body = {
        "fields": {
            "mode": _to_firestore_value(mode),
            "userId": _to_firestore_value(user_id),
            "sessionId": _to_firestore_value(session_id),
            "relationshipId": _to_firestore_value(relationship_id or ""),
            "role": _to_firestore_value(role),
            "content": _to_firestore_value(content),
            "createdAt": _to_firestore_value(now),
        }
    }
    _request_json("POST", f"chat_sessions/{doc_id}/turns", body=body)


def load_chat_turns(
    *,
    mode: str,
    user_id: str,
    session_id: str,
    relationship_id: Optional[str],
    limit: int = 12,
) -> List[Dict[str, str]]:
    doc_id = _session_doc_id(mode, user_id, session_id, relationship_id)
    payload = _request_json(
        "GET",
        f"chat_sessions/{doc_id}/turns",
        query={"pageSize": str(limit), "orderBy": "createdAt desc"},
    )
    if not payload:
        return []

    docs = payload.get("documents", [])
    turns: List[Dict[str, str]] = []
    for doc in docs:
        fields = doc.get("fields", {})
        role = _from_firestore_value(fields.get("role", {}))
        content = _from_firestore_value(fields.get("content", {}))
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            turns.append({"role": role, "content": content})
    turns.reverse()
    return turns[-limit:]


def load_daily_usage(user_id: str, day: str) -> Optional[Dict[str, float]]:
    doc_id = _usage_doc_id(user_id, day)
    payload = _request_json("GET", f"usage_daily/{doc_id}")
    fields = _extract_fields(payload)
    if not fields:
        return None

    tokens = _from_firestore_value(fields.get("tokens", {}))
    cost_usd = _from_firestore_value(fields.get("costUsd", {}))
    return {
        "tokens": float(tokens or 0.0),
        "cost_usd": float(cost_usd or 0.0),
    }


def save_daily_usage(user_id: str, day: str, tokens: float, cost_usd: float) -> None:
    doc_id = _usage_doc_id(user_id, day)
    body = {
        "fields": {
            "userId": _to_firestore_value(user_id),
            "day": _to_firestore_value(day),
            "tokens": _to_firestore_value(float(tokens)),
            "costUsd": _to_firestore_value(float(cost_usd)),
            "updatedAt": _to_firestore_value(datetime.now(timezone.utc)),
        }
    }
    _request_json("PATCH", f"usage_daily/{doc_id}", body=body)

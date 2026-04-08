from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
try:
    from app.core.request_context import set_current_user_id
except ModuleNotFoundError:  # Backward-compatible for deployments missing request_context module.
    def set_current_user_id(_user_id):
        return None


_bearer = HTTPBearer(auto_error=False)


def _normalize_identity_claim(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip()
    if normalized.lower() in {"", "unknown", "null", "none"}:
        return ""
    return normalized


def _resolve_user_id_from_claims(claims: Dict[str, Any]) -> str:
    # Prefer explicit uid-style claims first; some providers keep `sub` as placeholder.
    candidate_keys = ("uid", "user_id", "userId", "sub", "id")
    for key in candidate_keys:
        resolved = _normalize_identity_claim(claims.get(key))
        if resolved:
            return resolved
    return ""


def _load_public_key() -> str | None:
    public_key = os.getenv("AUTH_JWT_PUBLIC_KEY")
    if public_key:
        return public_key.replace("\\n", "\n")
    return None


def _decode_jwt_token(token: str) -> Dict[str, Any]:
    audience = os.getenv("AUTH_JWT_AUDIENCE")
    issuer = os.getenv("AUTH_JWT_ISSUER")
    algorithms = [a.strip() for a in os.getenv("AUTH_JWT_ALGORITHMS", "HS256").split(",") if a.strip()]

    secret = os.getenv("AUTH_JWT_SECRET")
    key = _load_public_key() or secret
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth is not configured",
        )

    options = {"verify_aud": bool(audience), "verify_iss": bool(issuer)}
    try:
        return jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=audience,
            issuer=issuer,
            options=options,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc


def _decode_firebase_token(token: str) -> Dict[str, Any]:
    try:
        request = google_requests.Request()
        claims = google_id_token.verify_firebase_token(token, request)
    except google_auth_exceptions.GoogleAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc

    project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if project_id and claims.get("aud") != project_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    return claims


def _decode_token(token: str) -> Dict[str, Any]:
    firebase_enabled = os.getenv("AUTH_FIREBASE_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    last_exc: HTTPException | None = None

    if firebase_enabled:
        try:
            return _decode_firebase_token(token)
        except HTTPException as exc:
            last_exc = exc

    legacy_key = _load_public_key() or os.getenv("AUTH_JWT_SECRET")
    if legacy_key:
        return _decode_jwt_token(token)

    if last_exc is not None:
        raise last_exc

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server auth is not configured",
    )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    claims = _decode_token(credentials.credentials)
    user_id = _resolve_user_id_from_claims(claims)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity",
        )
    # Make user identity available to downstream telemetry/safety layers in this request.
    set_current_user_id(user_id)
    return user_id


def _is_admin_claims(claims: Dict[str, Any]) -> bool:
    role = str(claims.get("role") or "").strip().lower()
    if role in {"admin", "super_admin", "superadmin"}:
        return True

    if claims.get("admin") is True or claims.get("is_admin") is True:
        return True

    roles = claims.get("roles")
    if isinstance(roles, list):
        role_set = {str(item).strip().lower() for item in roles}
        if "admin" in role_set or "super_admin" in role_set or "superadmin" in role_set:
            return True

    allowlist_raw = os.getenv("ADMIN_EMAILS", "")
    allowlist = {email.strip().lower() for email in allowlist_raw.split(",") if email.strip()}
    email = str(claims.get("email") or "").strip().lower()
    if allowlist and email in allowlist:
        return True

    return False


def require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="x-admin-key"),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> bool:
    expected = (os.getenv("ADMIN_API_KEY") or "").strip()
    if expected and x_admin_key == expected:
        return True

    if credentials is not None and credentials.scheme.lower() == "bearer":
        claims = _decode_token(credentials.credentials)
        if _is_admin_claims(claims):
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authorization required",
    )

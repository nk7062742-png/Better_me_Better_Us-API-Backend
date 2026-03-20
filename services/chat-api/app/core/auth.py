import os
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt


_bearer = HTTPBearer(auto_error=False)


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
    user_id = claims.get("sub") or claims.get("uid") or claims.get("user_id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identity",
        )
    return user_id

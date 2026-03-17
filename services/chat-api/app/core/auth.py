import os
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt


_bearer = HTTPBearer(auto_error=False)


def _load_public_key() -> str | None:
    public_key = os.getenv("AUTH_JWT_PUBLIC_KEY")
    if public_key:
        return public_key.replace("\\n", "\n")
    return None


def _decode_token(token: str) -> Dict[str, Any]:
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

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional


_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)


def set_current_user_id(user_id: Optional[str]) -> Token:
    normalized = user_id.strip() if isinstance(user_id, str) else user_id
    return _current_user_id.set(normalized or None)


def get_current_user_id() -> Optional[str]:
    return _current_user_id.get()


def reset_current_user_id(token: Token) -> None:
    _current_user_id.reset(token)

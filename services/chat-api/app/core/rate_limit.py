import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, status, Request

# Simple in-memory sliding window rate limiter (per process).
# Defaults are conservative; adjust via env if needed later.
WINDOW_SECONDS = 60
MAX_REQUESTS = 120  # per key/IP per window

_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _make_key(request: Request) -> str:
    # Use client IP; fall back to "anonymous" if unavailable.
    return request.client.host or "anonymous"


async def enforce_rate_limit(
    request: Request,
) -> None:
    now = time.time()
    key = _make_key(request)
    dq = _hits[key]
    # Drop timestamps outside window
    while dq and dq[0] < now - WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again shortly.",
        )
    dq.append(now)

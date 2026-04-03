from __future__ import annotations

import os
from fastapi import APIRouter, Depends, Header, HTTPException, status
from typing import Optional

try:
    from app.core.auth import require_admin_key
except ImportError:
    def require_admin_key(
        x_admin_key: str | None = Header(default=None, alias="x-admin-key"),
    ) -> bool:
        expected = os.getenv("ADMIN_API_KEY")
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Admin auth is not configured",
            )
        if x_admin_key != expected:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin key",
            )
        return True

from app.core.rate_limit import enforce_rate_limit
from app.core.qdrant_db import KB_COLLECTIONS, MEMORY_COLLECTIONS, client
from app.core.telemetry import error_logs, metrics, moderation_logs, budget_usage

router = APIRouter(prefix="/admin", tags=["admin"])


def _collection_size(collection_name: str) -> Optional[int]:
    info = client.get_collection(collection_name=collection_name)
    return getattr(info, "points_count", None)


@router.get("/status")
def status(_admin=Depends(require_admin_key), _rl=Depends(enforce_rate_limit)):
    kb_sizes = {mode: _collection_size(name) for mode, name in KB_COLLECTIONS.items()}
    memory_sizes = {mode: _collection_size(name) for mode, name in MEMORY_COLLECTIONS.items()}
    return {
        "metrics": metrics,
        "kb_collection_sizes": kb_sizes,
        "memory_collection_sizes": memory_sizes,
        "error_logs": error_logs[-20:],
        "moderation_logs": moderation_logs[-20:],
        "budget_usage": budget_usage(),
    }


@router.get("/metrics")
def metrics_endpoint(_admin=Depends(require_admin_key), _rl=Depends(enforce_rate_limit)):
    """Basic metrics endpoint for cost governance & observability."""
    return {
        "metrics": metrics,
        "error_logs": error_logs[-50:],
        "moderation_logs": moderation_logs[-50:],
        "budget_usage": budget_usage(),
    }
 

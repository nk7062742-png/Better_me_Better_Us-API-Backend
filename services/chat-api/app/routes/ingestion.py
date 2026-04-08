from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends

from app.core.auth import get_current_user_id
from app.core.rate_limit import enforce_rate_limit
from app.core.modes import normalize_mode
from app.core.request_context import set_current_user_id, reset_current_user_id
from app.services.ingestion import ingest_document

router = APIRouter()


@router.post("/ingest")
async def ingest(
    mode: str = Form(...),
    source: str = Form(""),
    session_id: str | None = Form(None),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    _rl=Depends(enforce_rate_limit),
):
    user_ctx_token = set_current_user_id(user_id)
    try:
        content = await file.read()
        normalized_mode = normalize_mode(mode)
        result = ingest_document(
            mode=normalized_mode,
            filename=file.filename,
            content=content,
            source=source,
            user_id=user_id,
            session_id=session_id,
        )
        return {
            "filename": file.filename,
            "mode": normalized_mode,
            "user_id": user_id,
            "session_id": session_id,
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        reset_current_user_id(user_ctx_token)

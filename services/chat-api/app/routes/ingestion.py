from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends

from app.core.auth import get_current_user_id
from app.core.rate_limit import enforce_rate_limit
from app.core.modes import normalize_mode
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

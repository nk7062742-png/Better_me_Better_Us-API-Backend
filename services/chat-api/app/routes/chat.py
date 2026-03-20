from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.auth import get_current_user_id
from app.core.rate_limit import enforce_rate_limit
from app.core.modes import normalize_mode
from app.services.rag import run_rag

router = APIRouter()


class ChatRequest(BaseModel):
    mode: str
    message: str
    source: Optional[str] = None  # IMPORTANT for PDF retrieval
    session_id: str
    relationship_id: Optional[str] = None
    partner1: Optional[str] = None
    partner2: Optional[str] = None
    partner1_name: Optional[str] = None
    partner2_name: Optional[str] = None


@router.post("/chat")
def chat(
    payload: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    _rl=Depends(enforce_rate_limit),
):
    try:
        mode = normalize_mode(payload.mode)

        result = run_rag(
            mode=mode,
            query=payload.message,
            user_id=user_id,
            session_id=payload.session_id,
            relationship_id=payload.relationship_id,
            source=payload.source,  # pass source
            partner1=payload.partner1,
            partner2=payload.partner2,
            partner1_name=payload.partner1_name,
            partner2_name=payload.partner2_name,
        )

        return {
            "session_id": payload.session_id,
            "relationship_id": payload.relationship_id,
            "mode": mode,
            "source": payload.source,
            **result,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

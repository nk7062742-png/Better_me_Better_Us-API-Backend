import uuid
import inspect
from datetime import datetime, timezone
from typing import Dict, List, Optional

from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue

from app.core.qdrant_db import KB_COLLECTIONS, MEMORY_COLLECTIONS, client
from app.core.embeddings import get_embedding
from app.core.llm import ask_llm
from app.core.prompts import build_messages
from app.core.safety import evaluate_input, evaluate_output
from app.core.telemetry import inc, log_error
from app.services.ingestion import LAST_INGESTED_FILENAME


SESSION_HISTORY: Dict[str, List[Dict[str, str]]] = {}
SESSION_OWNERS: Dict[str, str] = {}


_MEMORY_BLOCKLIST = {
    "do not have access",
    "don't have access",
    "no access",
    "cannot access",
    "can't access",
    "no uploaded documents",
    "lack access",
}


def _extract_snippets(results) -> List[str]:
    return [p.payload.get("text", "") for p in results if p.payload.get("text")]


def _trim(snippets: List[str], max_chars: int = 1200) -> List[str]:
    output, total = [], 0
    for s in snippets:
        if total + len(s) > max_chars:
            break
        output.append(s)
        total += len(s)
    return output


def _filter_memory(snippets: List[str]) -> List[str]:
    cleaned: List[str] = []
    for s in snippets:
        lower = s.lower()
        if any(term in lower for term in _MEMORY_BLOCKLIST):
            continue
        cleaned.append(s)
    return cleaned


def _dedupe_preserve_order(snippets: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for snippet in snippets:
        key = snippet.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(snippet)
    return output


def _infer_emotion_tone(user_input: str) -> str:
    text = user_input.lower()
    if any(k in text for k in ("angry", "furious", "upset", "frustrated")):
        return "high_intensity"
    if any(k in text for k in ("sad", "hurt", "lonely", "overwhelmed", "anxious")):
        return "distressed"
    if any(k in text for k in ("confused", "unclear", "stuck")):
        return "uncertain"
    if any(k in text for k in ("grateful", "happy", "calm", "better")):
        return "positive"
    return "neutral"


def _compact(text: str, max_len: int = 220) -> str:
    value = " ".join((text or "").split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _build_memory_record(mode: str, user_input: str, reply: str) -> Dict[str, str]:
    emotion_tone = _infer_emotion_tone(user_input)
    user_focus = _compact(user_input, max_len=280)
    assistant_focus = _compact(reply, max_len=280)
    summary = _compact(
        f"In {mode}, user discussed: {user_focus}. Assistant guidance: {assistant_focus}.",
        max_len=420,
    )
    return {
        "schema": "memory_v1",
        "mode": mode,
        "summary": summary,
        "user_focus": user_focus,
        "assistant_focus": assistant_focus,
        "emotion_tone": emotion_tone,
    }


def _record_to_embedding_text(record: Dict[str, str]) -> str:
    return " | ".join(
        [
            f"summary: {record.get('summary', '')}",
            f"user_focus: {record.get('user_focus', '')}",
            f"assistant_focus: {record.get('assistant_focus', '')}",
            f"emotion_tone: {record.get('emotion_tone', 'neutral')}",
        ]
    )


def _bullets_from_context(snippets: List[str], n: int = 3, max_len: int = 220) -> List[str]:
    bullets: List[str] = []
    for text in snippets:
        if len(bullets) >= n:
            break
        trimmed = text.strip().replace("\n", " ")
        if len(trimmed) > max_len:
            trimmed = trimmed[: max_len - 3].rstrip() + "..."
        bullets.append(trimmed)
    return bullets


def _search(collection: str, vector: List[float], limit: int, flt: Optional[Filter] = None) -> List[str]:
    try:
        res = client.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
            query_filter=flt,
        )
        return _extract_snippets(getattr(res, "points", []))
    except Exception as exc:
        log_error("qdrant_search", f"collection={collection} failed: {exc}")
        return []


def _save_memory(
    mode: str,
    user_id: str,
    session_id: str,
    relationship_id: Optional[str],
    user_input: str,
    reply: str,
) -> None:
    record = _build_memory_record(mode, user_input, reply)
    memory_text = _record_to_embedding_text(record)
    vector = get_embedding(memory_text)

    client.upsert(
        collection_name=MEMORY_COLLECTIONS[mode],
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "user_id": user_id,
                    "session_id": session_id,
                    "relationship_id": relationship_id,
                    "mode": mode,
                    "text": memory_text,
                    "summary": record["summary"],
                    "user_focus": record["user_focus"],
                    "assistant_focus": record["assistant_focus"],
                    "emotion_tone": record["emotion_tone"],
                    "memory_schema": record["schema"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        ],
        wait=False,
    )


def _is_recent_upload_request(text: str) -> bool:
    lower = text.lower()
    return (
        "just uploaded" in lower
        or "uploaded" in lower
        or "the pdf" in lower
        or "the file" in lower
    )

def run_rag(
    *,
    mode: str,
    user_id: str,
    session_id: str,
    relationship_id: Optional[str] = None,
    query: Optional[str] = None,
    user_input: Optional[str] = None,
    source: Optional[str] = None,
    partner1: Optional[str] = None,
    partner2: Optional[str] = None,
) -> Dict[str, object]:
    text = (user_input or query or "").strip()
    if not text:
        raise ValueError("Message required")

    if mode not in KB_COLLECTIONS:
        raise ValueError(f"Invalid mode: {mode}")
    if not user_id:
        raise ValueError("user_id is required")
    if mode == "relationship_mediation" and not relationship_id:
        raise ValueError("relationship_id is required for mediation mode")
    existing_owner = SESSION_OWNERS.get(session_id)
    if existing_owner and existing_owner != user_id:
        raise ValueError("Invalid session_id for authenticated user")
    SESSION_OWNERS[session_id] = user_id

    safe, msg = evaluate_input(text)
    if not safe:
        return {"reply": msg, "context": [], "memory": []}

    doc_like = source is not None or _is_recent_upload_request(text) or any(
        kw in text.lower() for kw in ["pdf", "document", "file", "upload"]
    )

    context: List[str] = []
    embedding = None

    if doc_like:
        embedding = get_embedding(text)

        flt_conditions = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        if source:
            flt_conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))
        if session_id:
            flt_conditions.append(FieldCondition(key="session_id", match=MatchValue(value=session_id)))
        flt = Filter(must=flt_conditions)

        context = _trim(_search(KB_COLLECTIONS[mode], embedding, limit=8, flt=flt))

        recent_filename = LAST_INGESTED_FILENAME.get((mode, user_id))
        if _is_recent_upload_request(text) and recent_filename:
            must_filters = [
                FieldCondition(key="filename", match=MatchValue(value=recent_filename)),
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            ]
            if session_id:
                must_filters.append(FieldCondition(key="session_id", match=MatchValue(value=session_id)))
            filename_filter = Filter(must=must_filters)
            recent_snippets = _trim(
                _search(KB_COLLECTIONS[mode], embedding, limit=8, flt=filename_filter)
            )
            if recent_snippets:
                context = recent_snippets

    memory_snippets: List[str] = []
    if embedding is None:
        embedding = get_embedding(text)

    base_filters = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    if relationship_id:
        base_filters.append(
            FieldCondition(key="relationship_id", match=MatchValue(value=relationship_id))
        )

    memory_raw: List[str] = []
    if session_id:
        session_filter = Filter(
            must=[
                *base_filters,
                FieldCondition(key="session_id", match=MatchValue(value=session_id)),
            ]
        )
        memory_raw.extend(_search(MEMORY_COLLECTIONS[mode], embedding, limit=3, flt=session_filter))

    long_term_filter = Filter(must=base_filters)
    memory_raw.extend(_search(MEMORY_COLLECTIONS[mode], embedding, limit=6, flt=long_term_filter))
    memory_snippets = _trim(
        _filter_memory(_dedupe_preserve_order(memory_raw)),
        max_chars=650,
    )
    history = SESSION_HISTORY.get(session_id, [])
    messages = build_messages(
    mode,
    text,
    history,
    context,
    memory_snippets,
    partner1=partner1,
    partner2=partner2,
)
    reply = ask_llm(messages, user_id=user_id)

    denial_markers = [
        "no content",
        "no context",
        "no access",
        "don't have access",
        "cannot access",
        "can't access",
        "lack access",
        "please provide more detail",
        "please share more details",
        "provide more details",
    ]
    if context and any(marker in reply.lower() for marker in denial_markers):
        bullets = _bullets_from_context(context, n=3)
        reply = "Here are key points from your document:\n- " + "\n- ".join(bullets)

    output_safe, output_msg = evaluate_output(reply)
    if not output_safe:
        reply = output_msg

    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": reply})
    SESSION_HISTORY[session_id] = history[-12:]

    _save_memory(mode, user_id, session_id, relationship_id, text, reply)
    inc("chat_requests", 1)

    return {
        "reply": reply,
        "context": context,
        "memory": memory_snippets,
        "relationship_id": relationship_id,
        "history": SESSION_HISTORY[session_id],
    }

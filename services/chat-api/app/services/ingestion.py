import io
import uuid
from typing import Dict, List

from docx import Document
from pypdf import PdfReader
from qdrant_client.models import PointStruct

from app.core.chunking import chunk_text_tokens
from app.core.qdrant_db import KB_COLLECTIONS, client
from app.core.embeddings import get_embeddings
from app.core.telemetry import inc
import os

# Tracks last file ingested per (mode, user) so chat requests like "the file I just uploaded"
# can be resolved without the user re-typing the filename.
LAST_INGESTED_FILENAME: Dict[tuple, str] = {}

def _extract_text_from_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages)


def _extract_text_from_docx(content: bytes) -> str:
    document = Document(io.BytesIO(content))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def _extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    if lower.endswith(".pdf"):
        return _extract_text_from_pdf(content)
    if lower.endswith(".docx"):
        return _extract_text_from_docx(content)
    raise ValueError("Unsupported file type. Use TXT, PDF, or DOCX.")


def ingest_document(
    *,
    mode: str,
    filename: str,
    content: bytes,
    source: str,
    user_id: str,
    session_id: str | None = None,
) -> Dict[str, int]:
    if mode not in KB_COLLECTIONS:
        raise ValueError(f"Invalid mode: {mode}")
    if not user_id:
        raise ValueError("user_id is required for ingestion")

    raw_text = _extract_text(filename, content)
    chunk_tokens = int(os.getenv("CHUNK_TOKENS", "800"))
    overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "120"))
    tokenizer_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    chunks: List[str] = chunk_text_tokens(
        raw_text,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
        model=tokenizer_model,
    )
    embeddings = get_embeddings(chunks)

    collection_name = KB_COLLECTIONS[mode]
    points = []
    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "mode": mode,
                    "text": chunk,
                    "user_id": user_id,
                    "session_id": session_id,
                    "source": source or filename,
                    "chunk_index": idx,
                    "filename": filename,
                },
            )
        )

    if points:
        client.upsert(collection_name=collection_name, points=points, wait=True)
        LAST_INGESTED_FILENAME[(mode, user_id)] = filename

    inc("ingestion_jobs", 1)
    inc("ingested_chunks", len(points))
    return {"chunks_indexed": len(points)}

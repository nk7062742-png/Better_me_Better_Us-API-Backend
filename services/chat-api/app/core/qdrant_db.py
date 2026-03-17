import os
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ROOT_ENV, override=False)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

if not QDRANT_URL or not QDRANT_API_KEY:
    raise RuntimeError("QDRANT_URL and QDRANT_API_KEY are required; set via secrets manager.")

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

KB_COLLECTIONS: Dict[str, str] = {
    "relationship_private": "relationship_private_vectors",
    "relationship_medication": "relationship_medication_vectors",
    "coaching": "coaching_vectors",
    "personal_growth": "personal_growth_vectors",
}

MEMORY_COLLECTIONS: Dict[str, str] = {
    "relationship_private": "relationship_private_memory",
    "relationship_medication": "relationship_medication_memory",
    "coaching": "coaching_memory",
    "personal_growth": "personal_growth_memory",
}


def _ensure_collection(name: str) -> None:
    collections = {item.name for item in client.get_collections().collections}
    if name in collections:
        info = client.get_collection(name)
        size = info.config.params.vectors.size
        if size != EMBEDDING_DIMENSION:
            # Drop and recreate with correct size
            client.delete_collection(collection_name=name)
            collections.remove(name)
        else:
            return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
    )


def _ensure_payload_indexes(collection: str) -> None:
    """Create keyword indexes for fields we filter on; ignore if they already exist."""
    for field in ("source", "filename", "mode", "session_id", "relationship_id", "user_id"):
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            # Likely already exists; keep going.
            continue


def ensure_collections() -> None:
    for collection in KB_COLLECTIONS.values():
        _ensure_collection(collection)
        _ensure_payload_indexes(collection)
    for collection in MEMORY_COLLECTIONS.values():
        _ensure_collection(collection)
        _ensure_payload_indexes(collection)


ensure_collections()

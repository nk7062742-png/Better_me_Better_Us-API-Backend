import os
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from app.core.telemetry import log_request

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ROOT_ENV, override=False)

OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_TEST_EMBEDDING_MODEL = os.getenv("OPENAI_TEST_EMBEDDING_MODEL", OPENAI_EMBEDDING_MODEL)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_TEST_BASE_URL = os.getenv("OPENAI_TEST_BASE_URL", OPENAI_BASE_URL)
OPENAI_ROUTE = os.getenv("OPENAI_ROUTE", "production").lower()
EMBEDDING_MAX_TOKENS = int(os.getenv("EMBEDDING_MAX_TOKENS", "8000"))
EMBEDDING_RETRY_LIMIT = int(os.getenv("EMBEDDING_RETRY_LIMIT", "3"))
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _resolve_openai_embedding_config() -> Tuple[str, str, Optional[str]]:
    route = "testing" if OPENAI_ROUTE in {"testing", "test"} else "production"
    if route == "testing":
        api_key = os.getenv("OPENAI_TEST_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = OPENAI_TEST_EMBEDDING_MODEL
        base_url = (OPENAI_TEST_BASE_URL or "").strip() or OPENAI_DEFAULT_BASE_URL
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        model = OPENAI_EMBEDDING_MODEL
        base_url = (OPENAI_BASE_URL or "").strip() or OPENAI_DEFAULT_BASE_URL

    if not api_key:
        if route == "testing":
            raise RuntimeError("OPENAI_TEST_API_KEY (or OPENAI_API_KEY fallback) not set")
        raise RuntimeError("OPENAI_API_KEY not set")

    return api_key, model, base_url


def _openai_client_and_model() -> Tuple[OpenAI, str]:
    api_key, model, base_url = _resolve_openai_embedding_config()
    kwargs = {"api_key": api_key, "base_url": base_url}
    return OpenAI(**kwargs), model


def get_embedding(text: str) -> List[float]:
    client, model = _openai_client_and_model()
    response = _embed_with_retry(client, model, text)
    return response.data[0].embedding


def get_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    client, model = _openai_client_and_model()
    response = _embed_with_retry(client, model, texts)
    return [item.embedding for item in response.data]


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    stop=stop_after_attempt(EMBEDDING_RETRY_LIMIT),
)
def _embed_with_retry(client: OpenAI, model: str, inputs) -> any:
    resp = client.embeddings.create(model=model, input=inputs)
    log_request(
        "embedding_call",
        {
            "model": model,
            "input_count": len(inputs) if isinstance(inputs, list) else 1,
        },
    )
    return resp

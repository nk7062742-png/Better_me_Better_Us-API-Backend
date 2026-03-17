import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from app.core.telemetry import log_usage, log_request

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ROOT_ENV, override=False)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEST_MODEL = os.getenv("OPENAI_TEST_MODEL", OPENAI_MODEL)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_TEST_BASE_URL = os.getenv("OPENAI_TEST_BASE_URL", OPENAI_BASE_URL)
OPENAI_ROUTE = os.getenv("OPENAI_ROUTE", "production").lower()
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_RETRY_LIMIT = int(os.getenv("LLM_RETRY_LIMIT", "3"))
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _resolve_openai_config() -> Tuple[str, str, Optional[str]]:
    route = "testing" if OPENAI_ROUTE in {"testing", "test"} else "production"
    if route == "testing":
        api_key = os.getenv("OPENAI_TEST_API_KEY") or os.getenv("OPENAI_API_KEY")
        model = OPENAI_TEST_MODEL
        base_url = (OPENAI_TEST_BASE_URL or "").strip() or OPENAI_DEFAULT_BASE_URL
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        model = OPENAI_MODEL
        base_url = (OPENAI_BASE_URL or "").strip() or OPENAI_DEFAULT_BASE_URL

    if not api_key:
        if route == "testing":
            raise RuntimeError("OPENAI_TEST_API_KEY (or OPENAI_API_KEY fallback) not set")
        raise RuntimeError("OPENAI_API_KEY not set")

    return api_key, model, base_url


def _openai_client_and_model() -> Tuple[OpenAI, str]:
    api_key, model, base_url = _resolve_openai_config()
    kwargs = {"api_key": api_key, "base_url": base_url}
    return OpenAI(**kwargs), model


def ask_llm(messages: List[Dict[str, str]], temperature: float = 0.4, user_id: Optional[str] = None) -> str:
    client, model = _openai_client_and_model()

    response = _chat_with_retry(client, model, messages, temperature)
    usage = getattr(response, "usage", None)
    if usage:
        log_usage(
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            user_id=user_id,
        )
    return response.choices[0].message.content or ""


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    stop=stop_after_attempt(LLM_RETRY_LIMIT),
)
def _chat_with_retry(client: OpenAI, model: str, messages: List[Dict[str, str]], temperature: float):
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=LLM_MAX_TOKENS,
    )
    log_request(
        "llm_call",
        {
            "model": model,
            "temperature": temperature,
            "message_count": len(messages),
        },
    )
    return resp

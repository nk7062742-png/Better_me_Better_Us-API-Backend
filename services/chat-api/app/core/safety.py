import os
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv
from openai import OpenAI

from app.core.telemetry import log_moderation
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ROOT_ENV, override=False)

SELF_HARM_TERMS = {
    "suicide",
    "kill myself",
    "end my life",
    "self harm",
    "hurt myself",
}

VIOLENCE_TERMS = {
    "how to kill",
    "make a bomb",
    "stab",
    "shoot",
    "abuse",
}


def _moderate_openai(text: str) -> Tuple[bool, str, dict]:
    """Call OpenAI moderation; return (safe, message, raw_result)."""
    route = os.getenv("OPENAI_ROUTE", "production").lower()
    if route in {"testing", "test"}:
        api_key = os.getenv("OPENAI_TEST_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = (os.getenv("OPENAI_TEST_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip()
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()

    if not api_key:
        # Fail-safe: if moderation cannot run, block conservatively.
        return False, "Service unavailable: moderation not configured.", {}

    base_url = base_url or OPENAI_DEFAULT_BASE_URL
    client = OpenAI(api_key=api_key, base_url=base_url)
    result = client.moderations.create(model="omni-moderation-latest", input=text)
    flagged = result.results[0].flagged
    categories = result.results[0].categories
    category_scores = result.results[0].category_scores

    raw = {
        "flagged": flagged,
        "categories": categories,
        "scores": category_scores,
    }
    if not flagged:
        return True, "", raw

    if categories.get("self-harm", False):
        msg = (
            "I’m really glad you reached out. I can’t assist with self-harm. "
            "If you may act on these thoughts, call emergency services now. "
            "In the U.S. or Canada, call/text 988 for immediate support."
        )
    elif categories.get("violence", False):
        msg = "I can’t help with violence. I can help with safety planning and de-escalation resources."
    else:
        msg = "I can’t respond to that request."

    return False, msg, raw


def evaluate_input(user_text: str) -> Tuple[bool, str]:
    safe, msg, raw = _moderate_openai(user_text)
    if raw:
        log_moderation({"input_preview": user_text[:120], **raw})
    if not safe:
        return safe, msg

    # Keyword fallback as extra guard
    text = user_text.lower()
    if any(term in text for term in SELF_HARM_TERMS):
        return (
            False,
            "I am really glad you reached out. I cannot help with harming yourself. "
            "If you may act on these thoughts, call emergency services now. "
            "If you are in the U.S. or Canada, call or text 988 for immediate support.",
        )
    if any(term in text for term in VIOLENCE_TERMS):
        return (
            False,
            "I cannot help with violence or abuse. I can help with de-escalation, safety planning, and legal-support resources.",
        )
    return True, ""

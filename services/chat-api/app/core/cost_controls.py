import os
from datetime import datetime, timezone
from typing import Dict, Tuple

import tiktoken


class BudgetExceededError(Exception):
    pass


MAX_INPUT_TOKENS_PER_REQUEST = int(os.getenv("MAX_INPUT_TOKENS_PER_REQUEST", "3000"))
DAILY_TOKEN_BUDGET_PER_USER = int(os.getenv("DAILY_TOKEN_BUDGET_PER_USER", "50000"))
DAILY_COST_BUDGET_USD_PER_USER = float(os.getenv("DAILY_COST_BUDGET_USD_PER_USER", "3.0"))

_daily_usage: Dict[Tuple[str, str], Dict[str, float]] = {}


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def enforce_chat_budget(user_id: str, user_text: str) -> None:
    estimated_input_tokens = _estimate_tokens(user_text)
    if estimated_input_tokens > MAX_INPUT_TOKENS_PER_REQUEST:
        raise BudgetExceededError(
            f"Request too large ({estimated_input_tokens} tokens est). "
            f"Limit is {MAX_INPUT_TOKENS_PER_REQUEST} tokens."
        )

    key = (user_id, _today_key())
    current = _daily_usage.get(key, {"tokens": 0.0, "cost_usd": 0.0})
    if current["tokens"] >= DAILY_TOKEN_BUDGET_PER_USER:
        raise BudgetExceededError("Daily token budget reached for this account.")
    if current["cost_usd"] >= DAILY_COST_BUDGET_USD_PER_USER:
        raise BudgetExceededError("Daily cost budget reached for this account.")


def record_usage(user_id: str | None, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None:
    if not user_id:
        return
    key = (user_id, _today_key())
    current = _daily_usage.setdefault(key, {"tokens": 0.0, "cost_usd": 0.0})
    current["tokens"] += float(prompt_tokens + completion_tokens)
    current["cost_usd"] += float(cost_usd)


def usage_snapshot() -> Dict[str, Dict[str, float]]:
    # Export with stable string keys for admin/debug use.
    return {
        f"{user_id}:{day}": {"tokens": values["tokens"], "cost_usd": values["cost_usd"]}
        for (user_id, day), values in _daily_usage.items()
    }

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.cost_controls import record_usage, usage_snapshot
from app.core.firestore_bridge import sync_moderation_event

# Simple in-memory counters; in production ship these to real telemetry.
metrics: Dict[str, Any] = {
    "chat_requests": 0,
    "ingestion_jobs": 0,
    "ingested_chunks": 0,
    "errors": 0,
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_cost_usd": 0.0,
}

error_logs: List[Dict[str, str]] = []
moderation_logs: List[Dict[str, Any]] = []

# Rough cost table (USD per 1K tokens). Adjust per provider/model if needed.
MODEL_PRICING = {
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0.0},
}


def inc(metric: str, value: Any = 1) -> None:
    metrics[metric] = metrics.get(metric, 0) + value


def log_error(source: str, message: str) -> None:
    inc("errors")
    error_logs.append(
        {
            "source": source,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def log_request(event: str, data: Dict[str, Any]) -> None:
    """Emit a structured JSON line."""
    payload = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **data}
    print(json.dumps(payload, default=str))


def log_usage(model: str, prompt_tokens: int, completion_tokens: int, user_id: Optional[str]) -> None:
    inc("total_prompt_tokens", prompt_tokens)
    inc("total_completion_tokens", completion_tokens)

    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4o-mini"))
    cost = (
        (prompt_tokens / 1000.0) * pricing.get("prompt", 0)
        + (completion_tokens / 1000.0) * pricing.get("completion", 0)
    )
    inc("total_cost_usd", cost)
    record_usage(user_id, prompt_tokens, completion_tokens, cost)

    log_request(
        "token_usage",
        {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": round(cost, 6),
            "user_id": user_id,
        },
    )


def log_moderation(result: Dict[str, Any]) -> None:
    moderation_logs.append(result)
    log_request("moderation", result)
    sync_moderation_event(result)


def budget_usage() -> Dict[str, Dict[str, float]]:
    return usage_snapshot()

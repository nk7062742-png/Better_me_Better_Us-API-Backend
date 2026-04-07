import pytest

from app.core import cost_controls


def test_enforce_chat_budget_blocks_when_projected_tokens_cross_daily_limit(monkeypatch):
    monkeypatch.setattr(cost_controls, "DAILY_TOKEN_BUDGET_PER_USER", 100)
    monkeypatch.setattr(cost_controls, "_estimate_tokens", lambda _text: 20)
    monkeypatch.setattr(cost_controls, "_today_key", lambda: "2026-04-07")
    monkeypatch.setattr(
        cost_controls,
        "load_daily_usage",
        lambda user_id, day: {"tokens": 90.0, "cost_usd": 0.0},
    )
    cost_controls._daily_usage.clear()

    with pytest.raises(cost_controls.BudgetExceededError):
        cost_controls.enforce_chat_budget(user_id="u1", user_text="hello")


def test_enforce_chat_budget_passes_when_under_limits(monkeypatch):
    monkeypatch.setattr(cost_controls, "DAILY_TOKEN_BUDGET_PER_USER", 100)
    monkeypatch.setattr(cost_controls, "_estimate_tokens", lambda _text: 9)
    monkeypatch.setattr(cost_controls, "_today_key", lambda: "2026-04-07")
    monkeypatch.setattr(
        cost_controls,
        "load_daily_usage",
        lambda user_id, day: {"tokens": 90.0, "cost_usd": 0.0},
    )
    cost_controls._daily_usage.clear()

    cost_controls.enforce_chat_budget(user_id="u1", user_text="hello")

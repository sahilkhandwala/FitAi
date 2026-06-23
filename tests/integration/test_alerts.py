"""
Integration tests for flows/alerts.py.

Tests verify:
- lunch_alert_flow sends Telegram when no breakfast/lunch logged
- lunch_alert_flow does NOT send when breakfast and lunch are both logged
- dinner_alert_flow sends Telegram when no dinner logged
- dinner_alert_flow does NOT send when dinner is logged

Uses prefect_test_harness() for in-process flow execution.
DB is an in-memory SQLite via the session fixture from conftest.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from prefect.testing.utilities import prefect_test_harness
from datetime import datetime
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_meal(session, meal_type: str):
    """Insert a meal log row for today using the queries layer."""
    from db import queries

    now = datetime.now(LA)
    queries.insert_meal_log(
        session,
        date=str(now.date()),
        meal_type=meal_type,
        logged_at=now.isoformat(),
        foods_identified=["test food"],
        macros={"calories": 500, "protein_g": 20, "carbs_g": 60, "fat_g": 15},
        flags={},
        score=7,
    )


def _patch_db(monkeypatch, session):
    """
    Make flows/alerts.py use the in-memory test session instead of
    opening a real SQLite file.
    """
    from unittest.mock import MagicMock

    fake_engine = MagicMock()
    fake_session_factory = MagicMock(return_value=session)

    monkeypatch.setattr("flows.alerts.get_engine", lambda: fake_engine)
    monkeypatch.setattr("flows.alerts.get_session_factory", lambda e: fake_session_factory)


def _patch_telegram(monkeypatch):
    """Capture requests.post calls to Telegram."""
    post_calls = []

    def fake_post(url, json=None, timeout=None):
        post_calls.append({"url": url, "json": json})
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr("requests.post", fake_post)
    return post_calls


# ---------------------------------------------------------------------------
# Lunch alert tests
# ---------------------------------------------------------------------------

class TestLunchAlert:
    def test_lunch_alert_sends_when_no_meals(self, session, monkeypatch):
        """Empty DB → lunch_alert_flow sends a Telegram alert."""
        _patch_db(monkeypatch, session)
        post_calls = _patch_telegram(monkeypatch)

        with prefect_test_harness():
            from flows.alerts import lunch_alert_flow
            lunch_alert_flow()

        telegram_calls = [c for c in post_calls if "sendMessage" in c["url"]]
        assert len(telegram_calls) == 1
        assert "breakfast or lunch" in telegram_calls[0]["json"]["text"]

    def test_lunch_alert_no_send_when_meals_logged(self, session, monkeypatch):
        """Breakfast logged → lunch_alert_flow does NOT send Telegram."""
        _insert_meal(session, "breakfast")
        _insert_meal(session, "lunch")
        _patch_db(monkeypatch, session)
        post_calls = _patch_telegram(monkeypatch)

        with prefect_test_harness():
            from flows.alerts import lunch_alert_flow
            lunch_alert_flow()

        telegram_calls = [c for c in post_calls if "sendMessage" in c["url"]]
        assert len(telegram_calls) == 0


# ---------------------------------------------------------------------------
# Dinner alert tests
# ---------------------------------------------------------------------------

class TestDinnerAlert:
    def test_dinner_alert_sends_when_no_dinner(self, session, monkeypatch):
        """Breakfast only → dinner_alert_flow sends a Telegram alert."""
        _insert_meal(session, "breakfast")
        _patch_db(monkeypatch, session)
        post_calls = _patch_telegram(monkeypatch)

        with prefect_test_harness():
            from flows.alerts import dinner_alert_flow
            dinner_alert_flow()

        telegram_calls = [c for c in post_calls if "sendMessage" in c["url"]]
        assert len(telegram_calls) == 1
        assert "dinner" in telegram_calls[0]["json"]["text"]

    def test_dinner_alert_no_send_when_dinner_logged(self, session, monkeypatch):
        """Dinner logged → dinner_alert_flow does NOT send Telegram."""
        _insert_meal(session, "dinner")
        _patch_db(monkeypatch, session)
        post_calls = _patch_telegram(monkeypatch)

        with prefect_test_harness():
            from flows.alerts import dinner_alert_flow
            dinner_alert_flow()

        telegram_calls = [c for c in post_calls if "sendMessage" in c["url"]]
        assert len(telegram_calls) == 0

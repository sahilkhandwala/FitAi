"""
E2E tests for lunch and dinner alert flows.

Tests verify:
1. lunch_alert_flow sends alert when no breakfast/lunch logged today
2. lunch_alert_flow sends no alert when lunch already logged
3. lunch_alert_flow sends no alert when breakfast already logged
4. dinner_alert_flow sends alert when no dinner logged
5. dinner_alert_flow sends no alert when dinner already logged

Uses prefect_test_harness to run flows without a real Prefect server.
Patches send_telegram_alert and queries.get_todays_meals so no real DB
or HTTP calls are made.
"""

import pytest
from prefect.testing.utilities import prefect_test_harness


@pytest.fixture(autouse=True, scope="module")
def prefect_harness():
    """Run all alert flow tests against an in-process ephemeral Prefect server."""
    with prefect_test_harness():
        yield


class _FakeMeal:
    """Minimal stand-in for a MealLog row — only meal_type is needed."""
    def __init__(self, meal_type: str):
        self.meal_type = meal_type


def _patch_alerts(monkeypatch):
    """
    Patch send_telegram_alert and get_todays_meals in the flows.alerts module.

    Returns:
        sent: list that captures each text string passed to the alert function.
        set_meals: callable — call with a list of meal_type strings to control
                   what get_todays_meals returns for the next flow run.
    """
    sent = []
    current_meals = []

    monkeypatch.setattr(
        "flows.alerts.send_telegram_alert",
        lambda text: sent.append(text),
    )
    monkeypatch.setattr(
        "flows.alerts.queries.get_todays_meals",
        lambda session: [_FakeMeal(m) for m in current_meals],
    )

    def set_meals(meal_types):
        current_meals.clear()
        current_meals.extend(meal_types)

    return sent, set_meals


class TestLunchAlertFlow:
    def test_alert_sent_when_no_meals_logged(self, monkeypatch):
        """lunch_alert_flow sends an alert when no breakfast or lunch is logged today."""
        sent, set_meals = _patch_alerts(monkeypatch)
        set_meals([])  # empty — no meals logged

        from flows.alerts import lunch_alert_flow
        lunch_alert_flow()

        assert len(sent) == 1
        assert "breakfast" in sent[0].lower() or "lunch" in sent[0].lower()

    def test_alert_sent_when_only_lunch_logged(self, monkeypatch):
        """lunch_alert_flow still alerts when only lunch is logged (breakfast missing)."""
        sent, set_meals = _patch_alerts(monkeypatch)
        set_meals(["lunch"])

        from flows.alerts import lunch_alert_flow
        lunch_alert_flow()

        assert len(sent) == 1

    def test_alert_sent_when_only_breakfast_logged(self, monkeypatch):
        """lunch_alert_flow still alerts when only breakfast is logged (lunch missing)."""
        sent, set_meals = _patch_alerts(monkeypatch)
        set_meals(["breakfast"])

        from flows.alerts import lunch_alert_flow
        lunch_alert_flow()

        assert len(sent) == 1

    def test_no_alert_when_both_breakfast_and_lunch_logged(self, monkeypatch):
        """lunch_alert_flow skips alert when both breakfast and lunch are logged."""
        sent, set_meals = _patch_alerts(monkeypatch)
        set_meals(["breakfast", "lunch"])

        from flows.alerts import lunch_alert_flow
        lunch_alert_flow()

        assert len(sent) == 0


class TestDinnerAlertFlow:
    def test_alert_sent_when_no_dinner_logged(self, monkeypatch):
        """dinner_alert_flow sends alert when no dinner is logged today."""
        sent, set_meals = _patch_alerts(monkeypatch)
        set_meals([])  # no meals at all

        from flows.alerts import dinner_alert_flow
        dinner_alert_flow()

        assert len(sent) == 1
        assert "dinner" in sent[0].lower()

    def test_no_alert_when_dinner_logged(self, monkeypatch):
        """dinner_alert_flow skips alert when dinner is already logged."""
        sent, set_meals = _patch_alerts(monkeypatch)
        set_meals(["dinner"])

        from flows.alerts import dinner_alert_flow
        dinner_alert_flow()

        assert len(sent) == 0

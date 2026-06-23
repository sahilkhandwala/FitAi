"""
Unit tests for pure pattern logic functions in bot/agents/pattern_detector.py.

These functions are module-level and need no DB or external deps.
Tests will fail with ImportError until bot/agents/pattern_detector.py exists.
"""

import pytest
from bot.agents.pattern_detector import get_escalation_tier, should_send_callout


class TestGetEscalationTier:
    def test_day_1_is_informational(self):
        assert get_escalation_tier(1) == "informational"

    def test_day_3_is_informational(self):
        assert get_escalation_tier(3) == "informational"

    def test_day_4_is_firm(self):
        assert get_escalation_tier(4) == "firm"

    def test_day_6_is_firm(self):
        assert get_escalation_tier(6) == "firm"

    def test_day_7_is_warning(self):
        assert get_escalation_tier(7) == "warning"

    def test_day_10_is_warning(self):
        assert get_escalation_tier(10) == "warning"

    def test_day_100_is_warning(self):
        assert get_escalation_tier(100) == "warning"


class TestShouldSendCallout:
    def test_not_in_list_returns_true(self):
        assert should_send_callout("high_gi_streak", "2026-06-20", []) is True

    def test_already_in_list_returns_false(self):
        assert should_send_callout(
            "high_gi_streak", "2026-06-20", ["high_gi_streak"]
        ) is False

    def test_different_pattern_returns_true(self):
        assert should_send_callout(
            "low_protein", "2026-06-20", ["high_gi_streak"]
        ) is True

    def test_multiple_callouts_not_in_list(self):
        sent = ["high_gi_streak", "low_fiber"]
        assert should_send_callout("low_protein", "2026-06-20", sent) is True

    def test_multiple_callouts_already_in_list(self):
        sent = ["high_gi_streak", "low_fiber", "low_protein"]
        assert should_send_callout("low_protein", "2026-06-20", sent) is False

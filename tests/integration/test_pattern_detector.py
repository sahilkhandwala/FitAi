"""
Integration tests for PatternDetectorAgent.

TDD: Written before implementation. Tests verify:
- Agent instantiates without error
- Agent invoke returns messages
- get_escalation_tier(3) returns 'informational' (tests the existing pure function)
- Dedup: insert a pattern for today → get_sent_callouts returns it,
  should_send_callout returns False

Pure logic function tests (get_escalation_tier, should_send_callout) are already
covered in tests/unit/test_pattern_logic.py. These tests cover AGENT behaviour
and the DB-backed dedup path.

Patch target: bot.agents.base_agent.ChatAnthropic — same reasoning as daily_summary tests.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from datetime import date
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_anthropic(monkeypatch):
    """
    Patch bot.agents.base_agent.ChatAnthropic with a stub that:
    - Supports bind_tools (BaseAgent calls this on init)
    - Returns AIMessage with no tool_calls so LangGraph routes to END
    """
    class FakeLLM:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model", "stub")

        def bind_tools(self, tools, **kwargs):
            return self

        def invoke(self, messages, **kwargs):
            return AIMessage(content="stub pattern detector response")

    monkeypatch.setattr("bot.agents.base_agent.ChatAnthropic", FakeLLM)
    return FakeLLM


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPatternDetectorInstantiates:
    def test_pattern_detector_instantiates(self, monkeypatch):
        """PatternDetectorAgent() does not raise."""
        _make_fake_anthropic(monkeypatch)
        from bot.agents.pattern_detector import PatternDetectorAgent
        agent = PatternDetectorAgent()
        assert agent is not None


class TestPatternDetectorReturnsMessages:
    def test_pattern_detector_returns_messages(self, session, monkeypatch):
        """invoke with pattern_check state returns result with messages list."""
        from bot.agents.tool_registry import init_tools
        _make_fake_anthropic(monkeypatch)

        init_tools(session)
        from bot.agents.pattern_detector import PatternDetectorAgent
        agent = PatternDetectorAgent()

        state = {
            "input_type": "cron",
            "telegram_chat_id": 123456789,
            "messages": [HumanMessage(content="Check patterns")],
            "media_group_id": None,
            "photos": [],
            "analysis_result": None,
            "next_agent": None,
        }
        result = agent.invoke(state)
        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) > 0


class TestEscalationTierPureFunction:
    def test_escalation_tier_day3_returns_informational(self):
        """get_escalation_tier(3) returns 'informational'."""
        from bot.agents.pattern_detector import get_escalation_tier
        assert get_escalation_tier(3) == "informational"


class TestDedupPreventsDoubleCallout:
    def test_dedup_prevents_double_callout(self, session):
        """
        Insert a pattern for today → get_sent_callouts returns it →
        should_send_callout returns False.
        """
        from db import queries
        from bot.agents.pattern_detector import should_send_callout

        today = str(date.today())
        queries.insert_pattern(
            session,
            date=today,
            pattern_type="high_gi_streak",
            streak_days=3,
        )

        sent = queries.get_sent_callouts(session, today)
        assert "high_gi_streak" in sent
        assert should_send_callout("high_gi_streak", today, sent) is False

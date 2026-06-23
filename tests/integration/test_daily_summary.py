"""
Integration tests for DailySummaryAgent.

TDD: Written before implementation. Tests verify:
- Agent instantiates without error
- Agent handles no meals today
- Agent invoke returns messages
- Context injection: health_profile block appears in system_prompt when lab data is present

Patch target: bot.agents.base_agent.ChatAnthropic — because base_agent.py imports
ChatAnthropic at module top, patching langchain_anthropic.ChatAnthropic would have no
effect after the module is already imported.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_anthropic(monkeypatch):
    """
    Patch bot.agents.base_agent.ChatAnthropic with a stub that satisfies:
    - bind_tools(tools) → returns self (so BaseAgent.__init__ doesn't crash)
    - invoke(messages) → returns AIMessage with no tool_calls (routes to END)
    """
    class FakeLLM:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model", "stub")

        def bind_tools(self, tools, **kwargs):
            return self

        def invoke(self, messages, **kwargs):
            return AIMessage(content="stub daily summary response")

    monkeypatch.setattr("bot.agents.base_agent.ChatAnthropic", FakeLLM)
    return FakeLLM


def _insert_health_profile(session):
    """Insert a UserHealthProfile row using the queries layer."""
    from db import queries
    queries.insert_health_profile(
        session,
        report_date="2026-05-15",
        a1c=6.4,
        ldl=142,
        hdl=48,
        triglycerides=180,
        medications=["metformin 500mg"],
        bmi=25.6,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDailySummaryInstantiates:
    def test_daily_summary_instantiates(self, monkeypatch):
        """DailySummaryAgent() does not raise."""
        _make_fake_anthropic(monkeypatch)
        from bot.agents.daily_summary import DailySummaryAgent
        agent = DailySummaryAgent()
        assert agent is not None


class TestDailySummaryNoMeals:
    def test_daily_summary_handles_no_meals_today(self, session, monkeypatch):
        """No meal rows for today — agent invokes without error."""
        from bot.agents.tool_registry import init_tools
        _make_fake_anthropic(monkeypatch)

        init_tools(session)
        from bot.agents.daily_summary import DailySummaryAgent
        agent = DailySummaryAgent()

        state = {
            "input_type": "cron",
            "telegram_chat_id": 123456789,
            "messages": [HumanMessage(content="Run daily summary")],
            "media_group_id": None,
            "photos": [],
            "analysis_result": None,
            "next_agent": None,
        }
        result = agent.invoke(state)
        assert result is not None


class TestDailySummaryReturnsMessages:
    def test_daily_summary_returns_messages(self, session, monkeypatch):
        """invoke with cron state returns result with messages list."""
        from bot.agents.tool_registry import init_tools
        _make_fake_anthropic(monkeypatch)

        init_tools(session)
        from bot.agents.daily_summary import DailySummaryAgent
        agent = DailySummaryAgent()

        state = {
            "input_type": "cron",
            "telegram_chat_id": 123456789,
            "messages": [HumanMessage(content="Run daily summary now")],
            "media_group_id": None,
            "photos": [],
            "analysis_result": None,
            "next_agent": None,
        }
        result = agent.invoke(state)
        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) > 0


class TestDailySummaryContextInjection:
    def test_daily_summary_injects_health_profile_context(self, session, monkeypatch):
        """
        When a health profile row exists, _build_full_system_prompt() includes
        the LAB RESULTS context block. Context is loaded per-invocation (not at startup)
        so system_prompt itself stays static — we check the built prompt instead.
        """
        from bot.agents.tool_registry import init_tools
        _make_fake_anthropic(monkeypatch)

        _insert_health_profile(session)
        init_tools(session)

        from bot.agents.daily_summary import DailySummaryAgent
        agent = DailySummaryAgent()

        full_prompt = agent._build_full_system_prompt()
        assert "LAB RESULTS" in full_prompt

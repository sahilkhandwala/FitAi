"""
Integration tests for WeeklyReportAgent.

TDD: written before implementation.
Tests are designed to run with mock_anthropic (no real API calls).
"""

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(input_type: str = "cron", message: str = "generate weekly report"):
    """Build a minimal AgentState dict for testing."""
    return {
        "input_type": input_type,
        "telegram_chat_id": 123456789,
        "messages": [HumanMessage(content=message)],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }


def _insert_weekly_report(session, week_start="2026-06-15", score_delta=3):
    """Insert a WeeklyReport row into the test DB."""
    from db.models import WeeklyReport

    row = WeeklyReport(
        week_start=week_start,
        avg_dietary_score=65,
        score_delta=score_delta,
        recommendations=["Eat more fiber", "Walk 10k steps"],
        skip_comparison=0,
    )
    session.add(row)
    session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWeeklyReportInstantiation:
    def test_weekly_report_instantiates(self, mock_anthropic):
        """WeeklyReportAgent() does not raise."""
        from bot.agents.weekly_report import WeeklyReportAgent

        agent = WeeklyReportAgent()
        assert agent is not None

    def test_weekly_report_is_base_agent(self, mock_anthropic):
        """WeeklyReportAgent is a BaseAgent subclass."""
        from bot.agents.weekly_report import WeeklyReportAgent
        from bot.agents.base_agent import BaseAgent

        agent = WeeklyReportAgent()
        assert isinstance(agent, BaseAgent)

    def test_weekly_report_has_correct_model(self, mock_anthropic):
        """WeeklyReportAgent uses the Opus model (ANTHROPIC_MODEL_HEAVY)."""
        from bot.agents.weekly_report import WeeklyReportAgent
        from config import ANTHROPIC_MODEL_HEAVY

        agent = WeeklyReportAgent()
        assert agent.model_str == ANTHROPIC_MODEL_HEAVY

    def test_weekly_report_no_checkpointer(self, mock_anthropic):
        """WeeklyReportAgent does NOT use a checkpointer."""
        from bot.agents.weekly_report import WeeklyReportAgent

        agent = WeeklyReportAgent()
        assert agent.use_checkpointer is False


class TestWeeklyReportInvocation:
    def test_weekly_report_returns_messages(self, session, mock_anthropic):
        """invoke() with a weekly_report state returns a result with messages."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.weekly_report import WeeklyReportAgent

        init_tools(session)
        agent = WeeklyReportAgent()
        state = _make_state()
        result = agent.invoke(state)

        assert "messages" in result
        assert len(result["messages"]) >= 1

    def test_weekly_report_handles_no_prior_report(self, session, mock_anthropic):
        """When no previous weekly_report exists in DB, agent handles gracefully (Week 1)."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.weekly_report import WeeklyReportAgent

        init_tools(session)
        # Empty DB — no prior report
        agent = WeeklyReportAgent()
        state = _make_state()

        # Should not raise; Week 1 case is handled in the prompt
        result = agent.invoke(state)
        assert "messages" in result

    def test_weekly_report_with_prior_report(self, session, mock_anthropic):
        """When a prior weekly_report exists, agent invokes without error."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.weekly_report import WeeklyReportAgent

        _insert_weekly_report(session)
        init_tools(session)
        agent = WeeklyReportAgent()
        state = _make_state()
        result = agent.invoke(state)

        assert "messages" in result


class TestWeeklyReportContextInjection:
    def test_weekly_report_injects_knowledge_base(
        self, session, mock_anthropic, knowledge_base_dir, monkeypatch
    ):
        """
        With KNOWLEDGE_BASE_DIR monkeypatched to knowledge_base_dir,
        _build_full_system_prompt() contains knowledge base content.
        Context is loaded per-invocation — check the built prompt, not system_prompt.
        """
        from bot.agents.tool_registry import init_tools
        import bot.agents.tool_registry as tr
        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", knowledge_base_dir)
        init_tools(session)

        from bot.agents.weekly_report import WeeklyReportAgent
        agent = WeeklyReportAgent()
        prompt = agent._build_full_system_prompt()

        assert "KNOWLEDGE BASE" in prompt or "knowledge" in prompt.lower()
        assert "fiber" in prompt.lower() or "omega" in prompt.lower()

    def test_weekly_report_injects_all_five_context_blocks(
        self, session, mock_anthropic, knowledge_base_dir, monkeypatch
    ):
        """
        _build_full_system_prompt() contains all 5 context block headers.
        Context is loaded per-invocation from DB — check built prompt, not system_prompt.
        """
        from bot.agents.tool_registry import init_tools
        import bot.agents.tool_registry as tr
        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", knowledge_base_dir)
        init_tools(session)

        from bot.agents.weekly_report import WeeklyReportAgent
        agent = WeeklyReportAgent()
        prompt = agent._build_full_system_prompt()

        assert "LAB RESULTS" in prompt or "HEALTH PROFILE" in prompt or "lab" in prompt.lower()
        assert "USER PROFILE" in prompt
        assert "NUTRITION" in prompt
        assert "SEMANTIC MEMORY" in prompt or "semantic" in prompt.lower()
        assert "KNOWLEDGE BASE" in prompt or "knowledge" in prompt.lower()

    def test_weekly_report_system_prompt_contains_agent_instructions(self, mock_anthropic):
        """system_prompt includes the weekly_report.txt content."""
        from bot.agents.weekly_report import WeeklyReportAgent

        agent = WeeklyReportAgent()
        # The prompt text includes agent-specific instructions
        assert "weekly" in agent.system_prompt.lower() or "Sunday" in agent.system_prompt

"""
Integration tests for HealthInsightsAgent.

TDD: written before implementation.
HealthInsightsAgent is unique: use_checkpointer=True (multi-turn Q&A).
Tests run with mock_anthropic (no real API calls).
"""

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(message: str = "why am I tired?"):
    """Build a minimal AgentState dict for testing."""
    return {
        "input_type": "text",
        "telegram_chat_id": 123456789,
        "messages": [HumanMessage(content=message)],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }


def _insert_health_profile(session):
    """Insert a UserHealthProfile row into the test DB."""
    from db.models import UserHealthProfile

    row = UserHealthProfile(
        report_date="2026-05-15",
        a1c=6.4,
        ldl=142,
        hdl=48,
        triglycerides=180,
        medications=["metformin 500mg"],
        bmi=25.6,
    )
    session.add(row)
    session.commit()


def _insert_semantic_memory(session):
    """Insert semantic memory rows."""
    from db.models import UserSemanticMemory

    row = UserSemanticMemory(
        category="diet",
        fact="Sahil tends to eat high-GI dinners on weekdays.",
        confidence="high",
        evidence="Weekly meal log analysis",
        valid_from="2026-06-15",
        updated_at="2026-06-15",
    )
    session.add(row)
    session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthInsightsInstantiation:
    def test_health_insights_instantiates(self, mock_anthropic):
        """HealthInsightsAgent() does not raise."""
        from bot.agents.health_insights import HealthInsightsAgent

        agent = HealthInsightsAgent()
        assert agent is not None

    def test_health_insights_is_base_agent(self, mock_anthropic):
        """HealthInsightsAgent is a BaseAgent subclass."""
        from bot.agents.health_insights import HealthInsightsAgent
        from bot.agents.base_agent import BaseAgent

        agent = HealthInsightsAgent()
        assert isinstance(agent, BaseAgent)

    def test_health_insights_has_correct_model(self, mock_anthropic):
        """HealthInsightsAgent uses the Opus model (ANTHROPIC_MODEL_HEAVY)."""
        from bot.agents.health_insights import HealthInsightsAgent
        from config import ANTHROPIC_MODEL_HEAVY

        agent = HealthInsightsAgent()
        assert agent.model_str == ANTHROPIC_MODEL_HEAVY

    def test_health_insights_has_checkpointer_flag(self, mock_anthropic):
        """use_checkpointer is True — this agent is multi-turn."""
        from bot.agents.health_insights import HealthInsightsAgent

        agent = HealthInsightsAgent()
        assert agent.use_checkpointer is True


class TestHealthInsightsInvocation:
    def test_health_insights_returns_messages(self, session, mock_anthropic):
        """invoke() with 'why am I tired?' returns a result with messages."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.health_insights import HealthInsightsAgent

        init_tools(session)
        agent = HealthInsightsAgent()
        state = _make_state("why am I tired?")
        # Pass thread_id: required when checkpointer is active (LangGraph enforces this)
        result = agent.invoke(state, thread_id="test-thread-1")

        assert "messages" in result
        assert len(result["messages"]) >= 1

    def test_health_insights_handles_no_meal_data(self, session, mock_anthropic):
        """When no meal data exists for the last 2 days, agent does not crash."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.health_insights import HealthInsightsAgent

        init_tools(session)
        # Empty DB — no meals
        agent = HealthInsightsAgent()
        state = _make_state("why am I bloated?")

        # Agent should not raise; prompt says to ask Sahil what he ate if no data
        # Pass thread_id since checkpointer is active
        result = agent.invoke(state, thread_id="test-thread-no-meals")
        assert "messages" in result

    def test_health_insights_handles_general_health_question(self, session, mock_anthropic):
        """Agent handles various symptom questions without crashing."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.health_insights import HealthInsightsAgent

        init_tools(session)
        agent = HealthInsightsAgent()
        for i, question in enumerate(["why do I have no energy?", "why am I gassy?", "why am I bloated?"]):
            state = _make_state(question)
            result = agent.invoke(state, thread_id=f"test-thread-{i}")
            assert "messages" in result


class TestHealthInsightsContextInjection:
    def test_health_insights_injects_full_context(
        self, session, mock_anthropic, knowledge_base_dir, monkeypatch
    ):
        """
        With health profile inserted and KB dir monkeypatched,
        system_prompt contains all 5 context blocks.
        """
        import bot.agents.tool_registry as tr
        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", knowledge_base_dir)
        _insert_health_profile(session)

        from bot.agents.tool_registry import init_tools
        init_tools(session)

        from bot.agents.health_insights import HealthInsightsAgent

        agent = HealthInsightsAgent()
        # Context is per-invocation — check _build_full_system_prompt(), not system_prompt
        prompt = agent._build_full_system_prompt()

        # All 5 context blocks must be present
        assert "LAB RESULTS" in prompt or "HEALTH PROFILE" in prompt or "lab" in prompt.lower()
        assert "USER PROFILE" in prompt
        assert "NUTRITION" in prompt
        assert "SEMANTIC MEMORY" in prompt or "semantic" in prompt.lower()
        assert "KNOWLEDGE BASE" in prompt or "knowledge" in prompt.lower()

    def test_health_insights_injects_knowledge_base_content(
        self, session, mock_anthropic, knowledge_base_dir, monkeypatch
    ):
        """
        With KNOWLEDGE_BASE_DIR monkeypatched, KB content appears in _build_full_system_prompt().
        Context is per-invocation — check built prompt, not static system_prompt.
        """
        from bot.agents.tool_registry import init_tools
        import bot.agents.tool_registry as tr
        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", knowledge_base_dir)
        init_tools(session)

        from bot.agents.health_insights import HealthInsightsAgent

        agent = HealthInsightsAgent()
        prompt = agent._build_full_system_prompt()
        assert "fiber" in prompt.lower() or "omega" in prompt.lower()

    def test_health_insights_system_prompt_contains_agent_instructions(self, mock_anthropic):
        """system_prompt includes the health_insights.txt content."""
        from bot.agents.health_insights import HealthInsightsAgent

        agent = HealthInsightsAgent()
        # The prompt contains recognizable health insights instructions
        assert "tired" in agent.system_prompt.lower() or "symptom" in agent.system_prompt.lower() or "personalised" in agent.system_prompt.lower()


class TestHealthInsightsTools:
    def test_health_insights_has_expected_tools(self, mock_anthropic):
        """Agent is loaded with the correct tool set from YAML."""
        from bot.agents.health_insights import HealthInsightsAgent

        agent = HealthInsightsAgent()
        tool_names = {t.name for t in agent.tools}

        assert "query_last_2_days_meals" in tool_names
        assert "query_last_2_days_steps" in tool_names
        assert "query_last_2_days_sleep" in tool_names
        assert "ask_web_search_permission" in tool_names
        assert "send_telegram_msg" in tool_names

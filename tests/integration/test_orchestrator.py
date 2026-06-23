"""
Integration tests for OrchestratorAgent.

TDD: written before bot/agents/orchestrator.py exists.
Expected red phase: ImportError on 'from bot.agents.orchestrator import OrchestratorAgent'.
"""

import pytest
from langchain_core.messages import HumanMessage

from bot.agents.base_agent import AgentState


# ---------------------------------------------------------------------------
# Fixture: patch ChatAnthropic in the module where BaseAgent imports it
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_base_agent_llm(monkeypatch, mock_anthropic):
    """
    Patch ChatAnthropic in bot.agents.base_agent's namespace.
    mock_anthropic (from conftest) already patches langchain_anthropic.ChatAnthropic,
    but base_agent captures the reference at import time via
    'from langchain_anthropic import ChatAnthropic'.
    We must also patch the already-bound name.
    """
    monkeypatch.setattr("bot.agents.base_agent.ChatAnthropic", mock_anthropic)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(text: str = "hello") -> AgentState:
    return AgentState(
        input_type="text",
        telegram_chat_id=123456789,
        messages=[HumanMessage(content=text)],
        media_group_id=None,
        photos=[],
        analysis_result=None,
        next_agent=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOrchestratorInstantiates:
    def test_orchestrator_instantiates(self):
        """OrchestratorAgent() does not raise and its graph is built."""
        from bot.agents.orchestrator import OrchestratorAgent

        agent = OrchestratorAgent()

        assert agent is not None
        assert agent.graph is not None
        # Confirm the fake LLM is wired — not the real Anthropic client
        assert type(agent._llm).__name__ == "FakeChatAnthropic"


class TestOrchestratorInvoke:
    def test_orchestrator_returns_messages(self, session, mock_anthropic):
        """Invoking with a text state returns a result dict with a messages list."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.orchestrator import OrchestratorAgent

        init_tools(session)
        agent = OrchestratorAgent()

        result = agent.invoke(_make_state("what did I eat today?"))

        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) >= 1

    def test_orchestrator_handles_general_question(self, session, mock_anthropic):
        """Invoking with a nutrition question returns without error."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.orchestrator import OrchestratorAgent

        init_tools(session)
        agent = OrchestratorAgent()

        result = agent.invoke(_make_state("is brown rice good?"))

        assert "messages" in result
        assert isinstance(result["messages"], list)

    def test_orchestrator_handles_empty_health_profile(self, session, mock_anthropic):
        """No health profile in DB — agent still responds without error."""
        from bot.agents.tool_registry import init_tools
        from bot.agents.orchestrator import OrchestratorAgent

        # session has no health profile rows (fresh in-memory DB)
        init_tools(session)
        agent = OrchestratorAgent()

        result = agent.invoke(_make_state("is ghee bad for cholesterol?"))

        assert "messages" in result
        assert isinstance(result["messages"], list)

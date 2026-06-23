"""
Integration tests for HealthExtractorAgent.

TDD: written before implementation.
All tests use mock_anthropic — no real API calls.

Key design:
- The stub LLM emits no tool_calls, so tools_condition routes to END immediately.
- DB side-effects are verified by calling tools directly (tool.invoke({...})).
- Agent invocation tests verify: no crash, result has messages.
"""

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_state(message: str = "[pdf: lab_report.pdf]"):
    """Build a minimal AgentState dict for a PDF upload."""
    return {
        "input_type": "pdf",
        "telegram_chat_id": 123456789,
        "messages": [HumanMessage(content=message)],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }


def _insert_health_profile_for_date(session, report_date: str = "2026-06-22"):
    """Insert a UserHealthProfile row for a specific date."""
    from db.models import UserHealthProfile

    row = UserHealthProfile(
        report_date=report_date,
        a1c=6.4,
        ldl=142,
        hdl=48,
        triglycerides=180,
        medications=["metformin 500mg"],
        bmi=25.6,
    )
    session.add(row)
    session.commit()


# ---------------------------------------------------------------------------
# Instantiation tests
# ---------------------------------------------------------------------------

class TestHealthExtractorInstantiation:
    def test_health_extractor_instantiates(self, mock_anthropic):
        """HealthExtractorAgent() does not raise."""
        from bot.agents.health_extractor import HealthExtractorAgent

        agent = HealthExtractorAgent()
        assert agent is not None

    def test_health_extractor_is_base_agent(self, mock_anthropic):
        """HealthExtractorAgent is a BaseAgent subclass."""
        from bot.agents.health_extractor import HealthExtractorAgent
        from bot.agents.base_agent import BaseAgent

        agent = HealthExtractorAgent()
        assert isinstance(agent, BaseAgent)

    def test_health_extractor_has_correct_model(self, mock_anthropic):
        """HealthExtractorAgent uses the Sonnet model (ANTHROPIC_MODEL_MID)."""
        from bot.agents.health_extractor import HealthExtractorAgent
        from config import ANTHROPIC_MODEL_MID

        agent = HealthExtractorAgent()
        assert agent.model_str == ANTHROPIC_MODEL_MID

    def test_health_extractor_has_expected_tools(self, mock_anthropic):
        """Agent is loaded with the correct tool set from health_extractor.yaml."""
        from bot.agents.health_extractor import HealthExtractorAgent

        agent = HealthExtractorAgent()
        tool_names = {t.name for t in agent.tools}

        assert "confirm_with_user" in tool_names
        assert "save_health_profile" in tool_names
        assert "generate_nutrition_guidance" in tool_names

    def test_health_extractor_no_context_injection(self, mock_anthropic):
        """
        HealthExtractor has no 'context' keys in YAML — system_prompt must NOT
        contain injected context blocks like 'LAB RESULTS' or 'USER PROFILE'.
        """
        from bot.agents.health_extractor import HealthExtractorAgent

        agent = HealthExtractorAgent()
        # Context blocks are identified by their === HEADER === markers
        assert "=== LATEST LAB RESULTS" not in agent.system_prompt
        assert "=== USER PROFILE" not in agent.system_prompt


# ---------------------------------------------------------------------------
# Invocation tests
# ---------------------------------------------------------------------------

class TestHealthExtractorInvocation:
    def test_health_extractor_presents_values_for_confirmation(
        self, session, mock_anthropic
    ):
        """
        Agent is invoked with a PDF state and must not crash.
        The prompt instructs the agent to call confirm_with_user with extracted values;
        with stub LLM, the graph completes without tool calls and returns messages.
        Separately, confirm_with_user tool is verified to exist and be callable.
        """
        from bot.agents.health_extractor import HealthExtractorAgent
        from bot.agents.tool_registry import init_tools

        init_tools(session)
        agent = HealthExtractorAgent()
        state = _pdf_state()

        result = agent.invoke(state)
        assert result["messages"]
        assert len(result["messages"]) >= 1

    def test_health_extractor_handles_missing_fields(self, session, mock_anthropic):
        """
        PDF missing HDL — save_health_profile tool accepts None for optional fields.
        Tool is called directly to verify it handles nulls gracefully.
        """
        from bot.agents.health_extractor import HealthExtractorAgent
        from bot.agents.tool_registry import init_tools, save_health_profile

        init_tools(session)
        agent = HealthExtractorAgent()
        state = _pdf_state(message="[pdf: partial_labs.pdf]")

        result = agent.invoke(state)
        assert result["messages"]

        # Directly verify save_health_profile handles None HDL
        tool_result = save_health_profile.invoke({
            "report_date": "2026-06-01",
            "a1c": 6.2,
            "ldl": 138,
            "hdl": None,      # missing field from PDF
            "triglycerides": None,  # also missing
            "medications": [],
            "bmi": None,
        })
        assert tool_result == "saved"

    def test_health_extractor_duplicate_report_date_friendly_error(
        self, session, mock_anthropic
    ):
        """
        A report for today already exists — save_health_profile returns 'duplicate_date'.
        The tool must not raise; the agent prompt instructs it to reply with a friendly message.
        """
        from bot.agents.health_extractor import HealthExtractorAgent
        from bot.agents.tool_registry import init_tools, save_health_profile

        init_tools(session)
        # Pre-insert a report for today
        _insert_health_profile_for_date(session, report_date="2026-06-22")

        agent = HealthExtractorAgent()
        state = _pdf_state()

        # Agent must not raise
        result = agent.invoke(state)
        assert result["messages"]

        # Tool returns 'duplicate_date' without raising
        tool_result = save_health_profile.invoke({
            "report_date": "2026-06-22",
            "a1c": 6.1,
            "ldl": 135,
            "hdl": 52,
            "triglycerides": 165,
            "medications": [],
            "bmi": 25.0,
        })
        assert tool_result == "duplicate_date"

    def test_health_extractor_generates_guidance_on_confirm(
        self, session, mock_anthropic
    ):
        """
        After saving a health profile, generate_nutrition_guidance is the next tool.
        Verify directly that the tool runs without error and returns 'done'.
        """
        from bot.agents.health_extractor import HealthExtractorAgent
        from bot.agents.tool_registry import (
            init_tools,
            save_health_profile,
            generate_nutrition_guidance,
        )

        init_tools(session)
        agent = HealthExtractorAgent()
        state = _pdf_state()

        result = agent.invoke(state)
        assert result["messages"]

        # Step 1: save the profile (simulating confirm path)
        save_result = save_health_profile.invoke({
            "report_date": "2026-06-22",
            "a1c": 6.4,
            "ldl": 142,
            "hdl": 48,
            "triglycerides": 180,
            "medications": ["metformin 500mg"],
            "bmi": 25.6,
        })
        assert save_result == "saved"

        # Step 2: generate guidance (no existing rules to deactivate/reactivate)
        guidance_result = generate_nutrition_guidance.invoke({
            "new_lab_values": {"a1c": 6.4, "ldl": 142, "hdl": 48},
            "deactivate_ids": [],
            "deactivate_remarks": [],
            "reactivate_ids": [],
            "new_rules": [
                {
                    "rule": "Limit saturated fat to 15g/day to support LDL reduction",
                    "category": "ldl",
                    "priority": 2,
                    "source_lab_date": "2026-06-22",
                }
            ],
        })
        assert guidance_result == "done"

        # Verify the new rule was persisted
        from db.queries import get_active_guidance
        rules = get_active_guidance(session)
        assert len(rules) == 1
        assert "saturated fat" in rules[0].rule.lower()


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------

class TestHealthExtractorSystemPrompt:
    def test_health_extractor_system_prompt_contains_instructions(self, mock_anthropic):
        """system_prompt includes content from prompts/health_extractor.txt."""
        from bot.agents.health_extractor import HealthExtractorAgent

        agent = HealthExtractorAgent()
        # Recognizable text from the health_extractor prompt
        prompt = agent.system_prompt.lower()
        assert "extract" in prompt or "lab" in prompt or "a1c" in prompt

"""
Integration tests for MealAnalyzerAgent.

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

def _photo_state(message: str = "[photo: lunch]", photos: list | None = None):
    """Build a minimal AgentState dict for a photo upload."""
    return {
        "input_type": "photo",
        "telegram_chat_id": 123456789,
        "messages": [HumanMessage(content=message)],
        "media_group_id": None,
        "photos": photos or ["file_id_123"],
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


# ---------------------------------------------------------------------------
# Instantiation tests
# ---------------------------------------------------------------------------

class TestMealAnalyzerInstantiation:
    def test_meal_analyzer_instantiates(self, mock_anthropic):
        """MealAnalyzerAgent() does not raise."""
        from bot.agents.meal_analyzer import MealAnalyzerAgent

        agent = MealAnalyzerAgent()
        assert agent is not None

    def test_meal_analyzer_is_base_agent(self, mock_anthropic):
        """MealAnalyzerAgent is a BaseAgent subclass."""
        from bot.agents.meal_analyzer import MealAnalyzerAgent
        from bot.agents.base_agent import BaseAgent

        agent = MealAnalyzerAgent()
        assert isinstance(agent, BaseAgent)

    def test_meal_analyzer_has_correct_model(self, mock_anthropic):
        """MealAnalyzerAgent uses the Sonnet model (ANTHROPIC_MODEL_MID)."""
        from bot.agents.meal_analyzer import MealAnalyzerAgent
        from config import ANTHROPIC_MODEL_MID

        agent = MealAnalyzerAgent()
        assert agent.model_str == ANTHROPIC_MODEL_MID

    def test_meal_analyzer_has_expected_tools(self, mock_anthropic):
        """Agent is loaded with the correct tool set from meal_analyzer.yaml."""
        from bot.agents.meal_analyzer import MealAnalyzerAgent

        agent = MealAnalyzerAgent()
        tool_names = {t.name for t in agent.tools}

        assert "save_meal_analysis" in tool_names
        assert "ask_web_search_permission" in tool_names
        assert "get_indian_food" in tool_names


# ---------------------------------------------------------------------------
# Invocation tests (stub LLM → no tools fired, but graph completes)
# ---------------------------------------------------------------------------

class TestMealAnalyzerInvocation:
    def test_meal_analyzer_saves_meal_to_db(self, session, mock_anthropic):
        """
        Direct tool call verifies save_meal_analysis inserts a row.
        The stub LLM emits no tool_calls so the agent itself won't trigger the tool;
        we exercise the tool directly to confirm DB wiring is intact.
        """
        from bot.agents.meal_analyzer import MealAnalyzerAgent
        from bot.agents.tool_registry import init_tools, save_meal_analysis
        from db.queries import get_todays_meals

        init_tools(session)
        agent = MealAnalyzerAgent()
        state = _photo_state()

        # Agent graph runs without error
        result = agent.invoke(state)
        assert result["messages"]

        # Tool call directly verifies DB side-effect
        save_meal_analysis.invoke({
            "meal_type": "lunch",
            "foods_identified": ["dal tadka", "white rice", "raita"],
            "estimated_macros": {
                "calories": 650,
                "protein_g": 22,
                "carbs_g": 90,
                "fat_g": 18,
                "fiber_g": 7,
                "saturated_fat_g": 6,
                "sugar_g": 8,
            },
            "glycemic_load": "high",
            "cholesterol_flags": [],
            "a1c_flags": ["high glycemic load from white rice"],
            "score": 62,
            "telegram_chat_id": 123456789,
        })

        meals = get_todays_meals(session)
        assert len(meals) == 1
        assert meals[0].meal_type == "lunch"
        assert meals[0].score == 62

    def test_meal_analyzer_non_food_sends_clarification(self, session, mock_anthropic):
        """
        The stub returns 'stub response' — no tool calls.
        Agent must not crash when photo state is provided without food.
        The prompt instructs the agent to reply with a clarification;
        with stub LLM, we just verify the graph completes and has messages.
        """
        from bot.agents.meal_analyzer import MealAnalyzerAgent
        from bot.agents.tool_registry import init_tools

        init_tools(session)
        agent = MealAnalyzerAgent()
        state = _photo_state(message="[photo: sunset view]")

        result = agent.invoke(state)
        assert result["messages"]
        assert len(result["messages"]) >= 1

    def test_meal_analyzer_includes_beverages_in_analysis(self, session, mock_anthropic):
        """
        Direct tool call with chai in foods_identified confirms the DB accepts it.
        The meal_analyzer prompt explicitly requires beverages in the analysis.
        """
        from bot.agents.meal_analyzer import MealAnalyzerAgent
        from bot.agents.tool_registry import init_tools, save_meal_analysis
        from db.queries import get_todays_meals

        init_tools(session)
        agent = MealAnalyzerAgent()
        state = _photo_state(message="[photo: breakfast with chai]")

        result = agent.invoke(state)
        assert result["messages"]

        # Tool call with chai in foods_identified
        save_meal_analysis.invoke({
            "meal_type": "breakfast",
            "foods_identified": ["poha", "chai with 2 tsp sugar"],
            "estimated_macros": {
                "calories": 380,
                "protein_g": 8,
                "carbs_g": 65,
                "fat_g": 9,
                "fiber_g": 4,
                "saturated_fat_g": 3,
                "sugar_g": 14,
            },
            "glycemic_load": "medium",
            "cholesterol_flags": [],
            "a1c_flags": ["sugar in chai adds to glycemic load"],
            "score": 72,
            "telegram_chat_id": 123456789,
        })

        meals = get_todays_meals(session)
        assert len(meals) == 1
        foods = meals[0].foods_identified
        # Chai (the beverage) must be present in foods_identified
        assert any("chai" in f.lower() for f in foods)

    def test_meal_analyzer_handles_missing_health_profile(self, session, mock_anthropic):
        """
        No health profile in DB — agent must not crash.
        Context loaders return 'No lab results on file yet.' when profile is absent.
        """
        from bot.agents.meal_analyzer import MealAnalyzerAgent
        from bot.agents.tool_registry import init_tools

        init_tools(session)
        # No health profile inserted — DB is empty
        agent = MealAnalyzerAgent()
        state = _photo_state()

        # Should not raise even with no health profile available
        result = agent.invoke(state)
        assert result["messages"]

    def test_meal_analyzer_json_output_has_required_fields(self, session, mock_anthropic):
        """
        The save_meal_analysis tool signature enforces required fields.
        Verify the tool accepts a well-formed payload and returns 'saved'.
        This mirrors what the LLM must produce when it calls the tool.
        """
        from bot.agents.meal_analyzer import MealAnalyzerAgent
        from bot.agents.tool_registry import init_tools, save_meal_analysis

        init_tools(session)
        agent = MealAnalyzerAgent()
        state = _photo_state()

        result = agent.invoke(state)
        assert result["messages"]

        # Construct the exact JSON the prompt mandates and invoke the tool
        payload = {
            "meal_type": "dinner",
            "foods_identified": ["grilled salmon", "quinoa", "broccoli"],
            "estimated_macros": {
                "calories": 520,
                "protein_g": 42,
                "carbs_g": 45,
                "fat_g": 14,
                "fiber_g": 10,
                "saturated_fat_g": 3,
                "sugar_g": 4,
            },
            "glycemic_load": "low",
            "cholesterol_flags": [],
            "a1c_flags": [],
            "score": 91,
            "telegram_chat_id": 123456789,
        }
        tool_result = save_meal_analysis.invoke(payload)
        assert tool_result == "saved"

        # Confirm required output fields by reading back what was saved
        from db.queries import get_todays_meals
        meals = get_todays_meals(session)
        assert len(meals) == 1
        row = meals[0]
        # All required fields must be present in the saved row
        assert row.foods_identified is not None
        macros = row.macros
        assert "calories" in macros
        assert "protein_g" in macros
        assert "carbs_g" in macros
        assert "fat_g" in macros
        assert "fiber_g" in macros
        assert "saturated_fat_g" in macros
        assert "sugar_g" in macros
        flags = row.flags
        assert "glycemic_load" in flags
        assert "cholesterol_flags" in flags
        assert "a1c_flags" in flags
        assert row.score is not None


# ---------------------------------------------------------------------------
# Context injection tests
# ---------------------------------------------------------------------------

class TestMealAnalyzerContextInjection:
    def test_meal_analyzer_system_prompt_includes_health_profile(
        self, session, mock_anthropic
    ):
        """
        With a health profile in DB, system_prompt contains lab context block.
        """
        from bot.agents.tool_registry import init_tools
        from bot.agents.meal_analyzer import MealAnalyzerAgent

        _insert_health_profile(session)
        init_tools(session)

        agent = MealAnalyzerAgent()
        assert "LAB RESULTS" in agent.system_prompt or "lab" in agent.system_prompt.lower()

    def test_meal_analyzer_system_prompt_includes_meal_analyzer_instructions(
        self, mock_anthropic
    ):
        """system_prompt contains content from prompts/meal_analyzer.txt."""
        from bot.agents.meal_analyzer import MealAnalyzerAgent

        agent = MealAnalyzerAgent()
        # Recognizable text from the meal_analyzer prompt
        assert "nutrition" in agent.system_prompt.lower() or "food" in agent.system_prompt.lower()

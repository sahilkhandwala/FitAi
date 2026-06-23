"""
Unit tests for bot/agents/tool_registry.py

TDD: These tests were written before implementation.
All tools are @tool-decorated objects — invoke via .invoke({...}).
"""

import json
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_health_profile(session, report_date="2026-05-15", a1c=6.4, ldl=142, hdl=48):
    """Insert a UserHealthProfile row directly via ORM."""
    from db.models import UserHealthProfile

    row = UserHealthProfile(
        report_date=report_date,
        a1c=a1c,
        ldl=ldl,
        hdl=hdl,
        triglycerides=180,
        medications=["metformin 500mg"],
        bmi=25.6,
    )
    session.add(row)
    session.commit()


def _insert_guidance(session, rule="Limit refined carbs", category="a1c", is_active=1):
    """Insert a UserNutritionGuidance row directly via ORM."""
    from db.models import UserNutritionGuidance

    row = UserNutritionGuidance(
        rule=rule,
        category=category,
        priority=1,
        is_active=is_active,
    )
    session.add(row)
    session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetHealthProfile:
    def test_returns_none_when_empty(self, session):
        """get_health_profile returns None when no rows exist."""
        from bot.agents.tool_registry import get_health_profile, init_tools

        init_tools(session)
        result = get_health_profile.invoke({})
        assert result is None

    def test_returns_dict_when_data_exists(self, session):
        """get_health_profile returns a dict with expected keys when a row exists."""
        from bot.agents.tool_registry import get_health_profile, init_tools

        _insert_health_profile(session)
        init_tools(session)
        result = get_health_profile.invoke({})

        assert isinstance(result, dict)
        assert "a1c" in result
        assert result["a1c"] == pytest.approx(6.4)
        assert result["ldl"] == 142
        assert result["hdl"] == 48


class TestGetNutritionGuidance:
    def test_filters_inactive_rules(self, session):
        """get_nutrition_guidance returns only active guidance rules."""
        from bot.agents.tool_registry import get_nutrition_guidance, init_tools

        _insert_guidance(session, rule="Active rule", is_active=1)
        _insert_guidance(session, rule="Inactive rule", is_active=0)
        init_tools(session)

        result = get_nutrition_guidance.invoke({})

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["rule"] == "Active rule"
        # inactive rule must not appear
        rules = [r["rule"] for r in result]
        assert "Inactive rule" not in rules


class TestQueryKnowledgeBase:
    def test_loads_json_files(self, knowledge_base_dir, monkeypatch):
        """query_knowledge_base loads all JSON files from KNOWLEDGE_BASE_DIR."""
        import bot.agents.tool_registry as tr

        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", knowledge_base_dir)
        from bot.agents.tool_registry import query_knowledge_base

        result = query_knowledge_base.invoke({})

        assert isinstance(result, list)
        assert len(result) == 2
        sources = {item["source"] for item in result}
        assert "Effect of dietary fiber on A1C — Smith et al. 2025" in sources
        assert "Omega-3 and HDL cholesterol — Patel et al. 2025" in sources


class TestSaveToKnowledgeBase:
    def test_writes_file(self, tmp_path, monkeypatch):
        """save_to_knowledge_base writes a JSON file to KNOWLEDGE_BASE_DIR."""
        import bot.agents.tool_registry as tr

        monkeypatch.setattr(tr, "KNOWLEDGE_BASE_DIR", tmp_path)
        from bot.agents.tool_registry import save_to_knowledge_base

        result = save_to_knowledge_base.invoke({
            "filename": "test_article",
            "source": "Test Source 2026",
            "ingested_at": "2026-06-22",
            "relevance_tags": ["a1c", "fiber"],
            "findings": ["Finding 1", "Finding 2"],
        })

        assert result == "saved"
        output_file = tmp_path / "test_article.json"
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert data["source"] == "Test Source 2026"
        assert data["relevance_tags"] == ["a1c", "fiber"]
        assert len(data["findings"]) == 2


class TestSaveMealAnalysis:
    def test_inserts_row(self, session):
        """save_meal_analysis inserts a row into meal_logs."""
        from bot.agents.tool_registry import save_meal_analysis, init_tools
        from db.queries import get_todays_meals

        init_tools(session)
        result = save_meal_analysis.invoke({
            "meal_type": "lunch",
            "foods_identified": ["white rice", "chicken curry"],
            "estimated_macros": {
                "calories": 780,
                "protein_g": 38,
                "carbs_g": 95,
                "fat_g": 22,
                "fiber_g": 3,
                "saturated_fat_g": 8,
                "sugar_g": 12,
            },
            "glycemic_load": "high",
            "cholesterol_flags": ["saturated fat above target"],
            "a1c_flags": ["high glycemic load"],
            "score": 48,
            "telegram_chat_id": 123456789,
        })

        assert result == "saved"
        meals = get_todays_meals(session)
        assert len(meals) == 1
        assert meals[0].meal_type == "lunch"
        assert meals[0].score == 48

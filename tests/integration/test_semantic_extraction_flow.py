"""
Integration tests for flows/semantic_extraction.py.

Tests verify:
1. Flow saves extracted facts to user_semantic_memory
2. Flow replaces (not appends) existing memory
3. Flow handles LLM parse errors gracefully (saves empty list)
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage
from prefect.testing.utilities import prefect_test_harness

LA = ZoneInfo("America/Los_Angeles")


def _make_fake_llm(monkeypatch, response_content: str):
    """Stub ChatAnthropic to return the given content string."""
    class FakeLLM:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages, **kwargs):
            return AIMessage(content=response_content)

    monkeypatch.setattr("flows.semantic_extraction.ChatAnthropic", FakeLLM)
    return FakeLLM


def _insert_existing_memory(session):
    """Insert one existing semantic memory row."""
    from db import queries
    today = datetime.now(LA).strftime("%Y-%m-%d")
    queries.replace_semantic_memory(session, [
        {
            "category": "meal_pattern",
            "fact": "old fact that should be replaced",
            "confidence": "low",
            "evidence": None,
            "valid_from": today,
        }
    ])


def _insert_meals(session, n: int = 3):
    """Insert n meal log rows."""
    from db import queries
    today = datetime.now(LA).strftime("%Y-%m-%d")
    for i in range(n):
        queries.insert_meal_log(
            session,
            date=today,
            meal_type="lunch",
            logged_at=f"{today}T12:{i:02d}:00",
            foods_identified=[f"food_{i}"],
            macros={"calories": 400},
            flags={},
            score=7,
        )


def _two_facts_json():
    today = datetime.now(LA).strftime("%Y-%m-%d")
    return json.dumps([
        {"category": "meal_pattern", "fact": "fact 1", "confidence": "high",
         "evidence": None, "valid_from": today},
        {"category": "glucose", "fact": "fact 2", "confidence": "medium",
         "evidence": "meal logs", "valid_from": today},
    ])


class TestSemanticExtractionSavesFacts:
    def test_semantic_extraction_saves_facts(self, session, monkeypatch):
        """Insert meals, mock LLM to return 2 facts, verify 2 rows in user_semantic_memory."""
        import flows.semantic_extraction as flow_module
        from db.models import UserSemanticMemory
        from sqlalchemy import select

        _insert_meals(session, 3)
        _make_fake_llm(monkeypatch, _two_facts_json())

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)

        with prefect_test_harness():
            flow_module.semantic_extraction_flow()

        rows = session.execute(select(UserSemanticMemory)).scalars().all()
        assert len(rows) == 2
        facts = [r.fact for r in rows]
        assert "fact 1" in facts
        assert "fact 2" in facts


class TestSemanticExtractionReplacesOldMemory:
    def test_semantic_extraction_replaces_old_memory(self, session, monkeypatch):
        """Existing memory is fully replaced, not appended to."""
        import flows.semantic_extraction as flow_module
        from db.models import UserSemanticMemory
        from sqlalchemy import select

        _insert_existing_memory(session)
        today = datetime.now(LA).strftime("%Y-%m-%d")
        new_fact = json.dumps([
            {"category": "sleep", "fact": "new fact", "confidence": "high",
             "evidence": None, "valid_from": today},
        ])
        _make_fake_llm(monkeypatch, new_fact)

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)

        with prefect_test_harness():
            flow_module.semantic_extraction_flow()

        rows = session.execute(select(UserSemanticMemory)).scalars().all()
        assert len(rows) == 1
        assert rows[0].fact == "new fact"


class TestSemanticExtractionHandlesParseError:
    def test_semantic_extraction_handles_parse_error(self, session, monkeypatch):
        """When LLM returns invalid JSON, flow does not raise and memory is empty."""
        import flows.semantic_extraction as flow_module
        from db.models import UserSemanticMemory
        from sqlalchemy import select

        _make_fake_llm(monkeypatch, "not valid json at all")

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)

        with prefect_test_harness():
            flow_module.semantic_extraction_flow()  # must not raise

        rows = session.execute(select(UserSemanticMemory)).scalars().all()
        assert len(rows) == 0

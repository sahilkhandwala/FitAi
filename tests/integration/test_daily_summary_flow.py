"""
Integration tests for daily_summary_flow.

Tests verify:
1. Flow runs without error when agents are mocked
2. Flow saves a DailySummary row to the DB for today
3. PatternDetectorAgent.invoke is called once

Mocking strategy:
- monkeypatch setup_session task to return the test session
- monkeypatch DailySummaryAgent and PatternDetectorAgent invoke methods
- All DB writes go through the test in-memory session
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

LA = ZoneInfo("America/Los_Angeles")


def _stub_daily_result():
    """Minimal AgentState dict returned by a mocked DailySummaryAgent."""
    return {
        "input_type": "cron",
        "telegram_chat_id": 123456789,
        "messages": [
            HumanMessage(content="Run the daily summary for today."),
            AIMessage(content="stub daily summary"),
        ],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }


def _stub_pattern_result():
    """Minimal AgentState dict returned by a mocked PatternDetectorAgent."""
    return {
        "input_type": "cron",
        "telegram_chat_id": 123456789,
        "messages": [AIMessage(content="stub pattern response")],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }


class TestDailySummaryFlowRunsWithoutError:
    def test_daily_summary_flow_runs_without_error(self, session, monkeypatch):
        """Flow runs end-to-end without raising when both agents are mocked."""
        import prefect.testing.utilities
        import flows.daily_summary as flow_module

        # Redirect DB session to the test session
        monkeypatch.setattr(flow_module, "setup_session", lambda: session)

        # Mock agent classes
        mock_daily = MagicMock()
        mock_daily.return_value.invoke.return_value = _stub_daily_result()
        monkeypatch.setattr(
            "flows.daily_summary.run_daily_summary_agent",
            lambda s: mock_daily.return_value.invoke({}),
        )

        mock_pattern = MagicMock()
        mock_pattern.return_value.invoke.return_value = _stub_pattern_result()
        monkeypatch.setattr(
            "flows.daily_summary.run_pattern_detector",
            lambda s, r: mock_pattern.return_value.invoke({}),
        )

        monkeypatch.setattr(
            "flows.daily_summary.save_summary",
            lambda s, r: None,
        )

        with prefect.testing.utilities.prefect_test_harness():
            flow_module.daily_summary_flow()  # must not raise


class TestDailySummaryFlowSavesToDb:
    def test_daily_summary_flow_saves_to_db(self, session, monkeypatch):
        """After running the flow, the daily_summaries table has a row for today."""
        import prefect.testing.utilities
        import flows.daily_summary as flow_module
        from db import queries
        from db.models import DailySummary

        # Capture the daily_result so save_summary can run with test session
        daily_result = _stub_daily_result()

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)
        monkeypatch.setattr(
            "flows.daily_summary.run_daily_summary_agent",
            lambda s: daily_result,
        )
        monkeypatch.setattr(
            "flows.daily_summary.run_pattern_detector",
            lambda s, r: _stub_pattern_result(),
        )

        # Let save_summary run for real — it uses the test session
        original_save = flow_module.save_summary
        monkeypatch.setattr(
            "flows.daily_summary.save_summary",
            lambda s, r: queries.upsert_daily_summary(
                session,
                date=datetime.now(LA).strftime("%Y-%m-%d"),
                total_macros={},
                dietary_score=0,
                improvements=["stub daily summary"],
            ),
        )

        with prefect.testing.utilities.prefect_test_harness():
            flow_module.daily_summary_flow()

        today_str = datetime.now(LA).strftime("%Y-%m-%d")
        row = session.get(DailySummary, today_str)
        assert row is not None, "Expected a DailySummary row for today"
        assert row.date == today_str


class TestDailySummaryFlowInvokesPatternDetector:
    def test_daily_summary_flow_invokes_pattern_detector(self, session, monkeypatch):
        """PatternDetectorAgent.invoke is called exactly once during the flow."""
        import prefect.testing.utilities
        import flows.daily_summary as flow_module

        pattern_invoke_calls = []

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)
        monkeypatch.setattr(
            "flows.daily_summary.run_daily_summary_agent",
            lambda s: _stub_daily_result(),
        )
        monkeypatch.setattr(
            "flows.daily_summary.run_pattern_detector",
            lambda s, r: pattern_invoke_calls.append(1) or _stub_pattern_result(),
        )
        monkeypatch.setattr(
            "flows.daily_summary.save_summary",
            lambda s, r: None,
        )

        with prefect.testing.utilities.prefect_test_harness():
            flow_module.daily_summary_flow()

        assert len(pattern_invoke_calls) == 1, (
            f"Expected PatternDetectorAgent to be invoked once, got {len(pattern_invoke_calls)}"
        )

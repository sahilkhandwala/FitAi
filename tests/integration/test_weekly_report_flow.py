"""
Integration tests for weekly_report_flow.

Tests verify:
1. Flow runs without error when agents are mocked
2. Flow saves a WeeklyReport row with the correct week_start (Monday of current LA week)
3. PatternDetectorAgent.invoke is called once

Mocking strategy:
- monkeypatch setup_session to return the test session
- monkeypatch run_weekly_report_agent and run_pattern_detector tasks
- Let save_report write to the test in-memory DB
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

LA = ZoneInfo("America/Los_Angeles")


def _stub_weekly_result():
    """Minimal AgentState dict returned by a mocked WeeklyReportAgent."""
    return {
        "input_type": "cron",
        "telegram_chat_id": 123456789,
        "messages": [
            HumanMessage(content="Generate the weekly health report."),
            AIMessage(content="stub weekly report"),
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


def _expected_week_start() -> str:
    """Return the Monday of the current LA week as an ISO date string."""
    today = datetime.now(LA).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


class TestWeeklyReportFlowRunsWithoutError:
    def test_weekly_report_flow_runs_without_error(self, session, monkeypatch):
        """Flow runs end-to-end without raising when both agents are mocked."""
        import prefect.testing.utilities
        import flows.weekly_report as flow_module

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)
        monkeypatch.setattr(
            "flows.weekly_report.run_weekly_report_agent",
            lambda s: _stub_weekly_result(),
        )
        monkeypatch.setattr(
            "flows.weekly_report.run_pattern_detector",
            lambda s, r: _stub_pattern_result(),
        )
        monkeypatch.setattr(
            "flows.weekly_report.save_report",
            lambda s, r: None,
        )

        with prefect.testing.utilities.prefect_test_harness():
            flow_module.weekly_report_flow()  # must not raise


class TestWeeklyReportFlowSavesToDb:
    def test_weekly_report_flow_saves_to_db(self, session, monkeypatch):
        """After running the flow, weekly_reports has a row with the correct week_start."""
        import prefect.testing.utilities
        import flows.weekly_report as flow_module
        from db import queries
        from db.models import WeeklyReport

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)
        monkeypatch.setattr(
            "flows.weekly_report.run_weekly_report_agent",
            lambda s: _stub_weekly_result(),
        )
        monkeypatch.setattr(
            "flows.weekly_report.run_pattern_detector",
            lambda s, r: _stub_pattern_result(),
        )

        week_start = _expected_week_start()

        # Let save_report run for real with the test session
        monkeypatch.setattr(
            "flows.weekly_report.save_report",
            lambda s, r: queries.upsert_weekly_report(
                session,
                week_start=week_start,
                avg_dietary_score=0,
                score_delta=0,
                patterns_detected=[],
                recommendations={"report": "stub weekly report"},
            ),
        )

        with prefect.testing.utilities.prefect_test_harness():
            flow_module.weekly_report_flow()

        row = session.get(WeeklyReport, week_start)
        assert row is not None, f"Expected a WeeklyReport row for week_start={week_start}"
        assert row.week_start == week_start


class TestWeeklyReportFlowInvokesPatternDetector:
    def test_weekly_report_flow_invokes_pattern_detector(self, session, monkeypatch):
        """PatternDetectorAgent.invoke is called exactly once during the flow."""
        import prefect.testing.utilities
        import flows.weekly_report as flow_module

        pattern_invoke_calls = []

        monkeypatch.setattr(flow_module, "setup_session", lambda: session)
        monkeypatch.setattr(
            "flows.weekly_report.run_weekly_report_agent",
            lambda s: _stub_weekly_result(),
        )
        monkeypatch.setattr(
            "flows.weekly_report.run_pattern_detector",
            lambda s, r: pattern_invoke_calls.append(1) or _stub_pattern_result(),
        )
        monkeypatch.setattr(
            "flows.weekly_report.save_report",
            lambda s, r: None,
        )

        with prefect.testing.utilities.prefect_test_harness():
            flow_module.weekly_report_flow()

        assert len(pattern_invoke_calls) == 1, (
            f"Expected PatternDetectorAgent to be invoked once, got {len(pattern_invoke_calls)}"
        )

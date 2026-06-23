"""
weekly_report_flow — 8:00pm Sunday (scheduled via Prefect deploy).

Steps:
1. Set up DB session
2. init_tools(session)
3. Invoke WeeklyReportAgent
4. Extract report text from last AIMessage
5. Invoke PatternDetectorAgent
6. Save weekly report to DB (week_start = Monday of current LA week)
7. Close session

On any unhandled exception: send Telegram alert.
"""

import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage
from prefect import flow, task

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_MODEL_FAST
from db import get_engine, get_session_factory
from db import queries

LA = ZoneInfo("America/Los_Angeles")


def _send_failure_alert(flow_name: str) -> None:
    """Send a Telegram message when a flow fails."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"Flow failed: {flow_name}"},
            timeout=10,
        )
    except Exception:
        pass  # Don't raise inside error handler


def _get_week_start_la() -> str:
    """Return the ISO date string of Monday of the current LA week."""
    today = datetime.now(LA).date()
    # weekday(): Monday=0, Sunday=6
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


@task
def setup_session():
    """Create and return a DB session."""
    engine = get_engine()
    SessionFactory = get_session_factory(engine)
    return SessionFactory()


@task
def run_weekly_report_agent(session):
    """Invoke WeeklyReportAgent and return the result state."""
    from bot.agents.tool_registry import init_tools
    from bot.agents.weekly_report import WeeklyReportAgent

    init_tools(session)
    agent = WeeklyReportAgent()
    state = {
        "input_type": "cron",
        "telegram_chat_id": int(TELEGRAM_CHAT_ID),
        "messages": [HumanMessage(content="Generate the weekly health report.")],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }
    return agent.invoke(state)


@task
def run_pattern_detector(session, weekly_result):
    """Invoke PatternDetectorAgent with the weekly report result messages."""
    from bot.agents.pattern_detector import PatternDetectorAgent

    agent = PatternDetectorAgent()
    state = {
        "input_type": "cron",
        "telegram_chat_id": int(TELEGRAM_CHAT_ID),
        "messages": weekly_result["messages"],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }
    return agent.invoke(state)


@task
def save_report(session, weekly_result):
    """Extract report text from agent result and persist to weekly_reports table."""
    ai_messages = [m for m in weekly_result["messages"] if isinstance(m, AIMessage)]
    report_text = ai_messages[-1].content if ai_messages else ""

    week_start = _get_week_start_la()
    queries.upsert_weekly_report(
        session,
        week_start=week_start,
        avg_dietary_score=0,
        score_delta=0,
        patterns_detected=[],
        recommendations={"report": report_text},
    )


@flow(name="weekly_report", retries=2, retry_delay_seconds=60)
def weekly_report_flow():
    try:
        session = setup_session()
        weekly_result = run_weekly_report_agent(session)
        run_pattern_detector(session, weekly_result)
        save_report(session, weekly_result)
    except Exception:
        _send_failure_alert("weekly_report")
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass

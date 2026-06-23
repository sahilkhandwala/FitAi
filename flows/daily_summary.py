"""
daily_summary_flow — 11:30pm daily (scheduled via Prefect deploy).

Steps:
1. Set up DB session
2. init_tools(session)
3. Invoke DailySummaryAgent
4. Pass result to PatternDetectorAgent
5. Save daily summary to DB
6. Close session

On any unhandled exception: send Telegram alert.
"""

import requests
from datetime import datetime
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


@task
def setup_session():
    """Create and return a DB session."""
    engine = get_engine()
    SessionFactory = get_session_factory(engine)
    return SessionFactory()


@task
def run_daily_summary_agent(session):
    """Invoke DailySummaryAgent and return the result state."""
    from bot.agents.tool_registry import init_tools
    from bot.agents.daily_summary import DailySummaryAgent

    init_tools(session)
    agent = DailySummaryAgent()
    state = {
        "input_type": "cron",
        "telegram_chat_id": int(TELEGRAM_CHAT_ID),
        "messages": [HumanMessage(content="Run the daily summary for today.")],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }
    return agent.invoke(state)


@task
def run_pattern_detector(session, daily_result):
    """Invoke PatternDetectorAgent with the daily summary result messages."""
    from bot.agents.pattern_detector import PatternDetectorAgent

    agent = PatternDetectorAgent()
    state = {
        "input_type": "cron",
        "telegram_chat_id": int(TELEGRAM_CHAT_ID),
        "messages": daily_result["messages"],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }
    return agent.invoke(state)


@task
def save_summary(session, daily_result):
    """Extract summary text from agent result and persist to daily_summaries table."""
    ai_messages = [m for m in daily_result["messages"] if isinstance(m, AIMessage)]
    summary_text = ai_messages[-1].content if ai_messages else ""

    today_la_str = datetime.now(LA).strftime("%Y-%m-%d")
    queries.upsert_daily_summary(
        session,
        date=today_la_str,
        total_macros={},
        dietary_score=0,
        improvements=[summary_text],
    )


@flow(name="daily_summary", retries=2, retry_delay_seconds=60)
def daily_summary_flow():
    try:
        session = setup_session()
        daily_result = run_daily_summary_agent(session)
        run_pattern_detector(session, daily_result)
        save_summary(session, daily_result)
    except Exception:
        _send_failure_alert("daily_summary")
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass

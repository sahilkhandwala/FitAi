"""
semantic_extraction_flow — 6:00pm Sunday (scheduled via Prefect deploy).

Extracts key health facts from the last 90 days of meal logs and daily summaries,
then replaces user_semantic_memory with the new facts.
"""

import json
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from prefect import flow, task, get_run_logger
from prefect.exceptions import MissingContextError

from config import ANTHROPIC_MODEL_MID, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from db import get_engine, get_session_factory
from db import queries

LA = ZoneInfo("America/Los_Angeles")

_SYSTEM_PROMPT = (
    "You are extracting key health insights from 90 days of meal and health data for Sahil.\n"
    "Return a JSON array of objects, each with keys: category, fact, confidence, valid_from.\n"
    "  - category: one of 'meal_pattern', 'symptom', 'cholesterol', 'glucose', 'activity', 'sleep'\n"
    "  - fact: concise health fact or pattern (one sentence)\n"
    "  - confidence: 'high', 'medium', or 'low'\n"
    "  - valid_from: today's date in YYYY-MM-DD format\n"
    "Max 20 items. Focus on: A1C-relevant patterns, cholesterol patterns, meal timing, "
    "food preferences, symptom correlations.\n"
    "Return ONLY the JSON array, no other text."
)


def _get_logger():
    try:
        return get_run_logger()
    except MissingContextError:
        return logging.getLogger(__name__)


def _send_failure_alert(flow_name: str) -> None:
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"Flow failed: {flow_name}"},
            timeout=10,
        )
    except Exception:
        pass


@task
def setup_session():
    """Create and return a DB session."""
    engine = get_engine()
    SessionFactory = get_session_factory(engine)
    return SessionFactory()


@task
def fetch_meal_data(session) -> str:
    """Return last 90 days of meal logs as a formatted string."""
    logger = _get_logger()
    meals = queries.get_meals_last_n_days(session, 90)
    if not meals:
        logger.info("No meal data found for last 90 days")
        return "No meal data available."
    lines = []
    for m in meals:
        foods = ", ".join(m.foods_identified) if m.foods_identified else "unknown"
        lines.append(f"{m.date} [{m.meal_type}] {foods} — score: {m.score}")
    return "\n".join(lines)


@task
def fetch_summary_data(session) -> str:
    """Return last 90 days of daily summaries as a formatted string."""
    from sqlalchemy import select, desc
    from db.models import DailySummary

    logger = _get_logger()
    today = datetime.now(LA).date()
    cutoff = str(today.replace(year=today.year if today.month > 3 else today.year - 1))

    from datetime import timedelta
    cutoff = str((today - timedelta(days=89)).isoformat())

    try:
        result = session.execute(
            select(DailySummary)
            .where(DailySummary.date >= cutoff)
            .order_by(desc(DailySummary.date))
            .limit(90)
        )
        rows = result.scalars().all()
    except Exception as e:
        logger.warning(f"Could not fetch daily summaries: {e}")
        return "No summary data available."

    if not rows:
        return "No daily summaries available."
    lines = []
    for r in rows:
        improvements = "; ".join(r.improvements) if r.improvements else ""
        lines.append(f"{r.date} score={r.dietary_score}: {improvements}")
    return "\n".join(lines)


@task
def extract_facts(meal_data: str, summary_data: str) -> list[dict]:
    """Call Claude Sonnet to extract health facts from meal + summary data."""
    logger = _get_logger()
    today_str = datetime.now(LA).strftime("%Y-%m-%d")

    llm = ChatAnthropic(model=ANTHROPIC_MODEL_MID, max_tokens=2048)
    user_msg = (
        f"Meal data (last 90 days):\n{meal_data}\n\n"
        f"Daily summaries:\n{summary_data}\n\n"
        f"Today's date: {today_str}"
    )
    response = llm.invoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])

    try:
        facts = json.loads(response.content)
        if not isinstance(facts, list):
            raise ValueError("Expected a JSON array")
        logger.info(f"Extracted {len(facts)} health facts")
        return facts
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e} — using empty list")
        return []


@task
def save_facts(session, facts: list[dict]) -> None:
    """Replace semantic memory with the new facts."""
    logger = _get_logger()
    queries.replace_semantic_memory(session, facts)
    logger.info(f"Saved {len(facts)} semantic memory facts")


@flow(name="semantic_extraction", retries=2, retry_delay_seconds=60)
def semantic_extraction_flow():
    """6:00pm Sunday: extract health facts from 90 days → replace semantic memory."""
    try:
        session = setup_session()
        meal_data = fetch_meal_data(session)
        summary_data = fetch_summary_data(session)
        facts = extract_facts(meal_data, summary_data)
        save_facts(session, facts)
    except Exception:
        _send_failure_alert("semantic_extraction")
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass

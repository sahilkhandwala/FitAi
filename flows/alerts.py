"""
Alert flows — lunch (3:00pm) and dinner (10:30pm) daily, scheduled via Prefect deploy.

lunch_alert_flow: sends Telegram alert if no breakfast or lunch logged today.
dinner_alert_flow: sends Telegram alert if no dinner logged today.
"""

import requests
from prefect import flow, task, get_run_logger

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from db import get_engine, get_session_factory
from db import queries


def _on_flow_failure(flow, flow_run, state):
    """Send Telegram alert when a flow fails."""
    text = f"⚠️ {flow.name} failed: {state.message}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception:
        pass


@task
def send_telegram_alert(text: str) -> None:
    """Send an alert message to the configured Telegram chat."""
    logger = get_run_logger()
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=10,
    )
    resp.raise_for_status()
    logger.info(f"Alert sent: {text[:60]}")


@flow(name="lunch_alert", retries=2, retry_delay_seconds=60, on_failure=[_on_flow_failure])
def lunch_alert_flow():
    """3:00pm daily: alert if no breakfast or lunch logged today."""
    logger = get_run_logger()

    engine = get_engine()
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    try:
        meals = queries.get_todays_meals(session)
        logged_types = {m.meal_type for m in meals}
        missing = {"breakfast", "lunch"} - logged_types
        if missing:
            send_telegram_alert(
                "⚠️ No breakfast or lunch logged today. Don't forget to log your meals!"
            )
            logger.info("Lunch alert sent — missing meal types: %s", missing)
        else:
            logger.info("Lunch alert skipped — breakfast and lunch both logged")
    finally:
        session.close()


@flow(name="dinner_alert", retries=2, retry_delay_seconds=60, on_failure=[_on_flow_failure])
def dinner_alert_flow():
    """10:30pm daily: alert if no dinner logged today."""
    logger = get_run_logger()

    engine = get_engine()
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    try:
        meals = queries.get_todays_meals(session)
        logged_types = {m.meal_type for m in meals}
        if "dinner" not in logged_types:
            send_telegram_alert(
                "⚠️ No dinner logged today. Don't forget to log your dinner!"
            )
            logger.info("Dinner alert sent — dinner not logged")
        else:
            logger.info("Dinner alert skipped — dinner already logged")
    finally:
        session.close()

"""
Runs all scheduled Prefect flows using serve() — the Prefect 3.x approach.
This is a long-running process; run it via the prefect-worker systemd service.

Usage: PYTHONPATH=/opt/nutrition-bot /opt/nutrition-bot/venv/bin/python deployment/deploy_flows.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PREFECT_API_URL", "http://127.0.0.1:4200/api")

from prefect import serve
from flows.morning_report import morning_report_flow
from flows.alerts import lunch_alert_flow, dinner_alert_flow
from flows.daily_summary import daily_summary_flow
from flows.semantic_extraction import semantic_extraction_flow
from flows.weekly_report import weekly_report_flow


async def main():
    await serve(
        morning_report_flow.to_deployment(
            name="morning-report",
            cron="30 10 * * *",
            timezone="America/Los_Angeles",
        ),
        lunch_alert_flow.to_deployment(
            name="lunch-alert",
            cron="0 15 * * *",
            timezone="America/Los_Angeles",
        ),
        dinner_alert_flow.to_deployment(
            name="dinner-alert",
            cron="30 22 * * *",
            timezone="America/Los_Angeles",
        ),
        daily_summary_flow.to_deployment(
            name="daily-summary",
            cron="30 23 * * *",
            timezone="America/Los_Angeles",
        ),
        semantic_extraction_flow.to_deployment(
            name="semantic-extraction",
            cron="0 18 * * 0",
            timezone="America/Los_Angeles",
        ),
        weekly_report_flow.to_deployment(
            name="weekly-report",
            cron="0 20 * * 0",
            timezone="America/Los_Angeles",
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())

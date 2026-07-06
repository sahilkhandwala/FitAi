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
from prefect.client.schemas.schedules import CronSchedule
from flows.morning_report import morning_report_flow
from flows.alerts import lunch_alert_flow, dinner_alert_flow
from flows.daily_summary import daily_summary_flow
from flows.semantic_extraction import semantic_extraction_flow
from flows.weekly_report import weekly_report_flow


async def main():
    LA = "America/Los_Angeles"
    await serve(
        morning_report_flow.to_deployment(
            name="morning-report",
            schedules=[CronSchedule(cron="30 10 * * *", timezone=LA)],
        ),
        lunch_alert_flow.to_deployment(
            name="lunch-alert",
            schedules=[CronSchedule(cron="0 15 * * *", timezone=LA)],
        ),
        dinner_alert_flow.to_deployment(
            name="dinner-alert",
            schedules=[CronSchedule(cron="30 22 * * *", timezone=LA)],
        ),
        daily_summary_flow.to_deployment(
            name="daily-summary",
            schedules=[CronSchedule(cron="30 23 * * *", timezone=LA)],
        ),
        semantic_extraction_flow.to_deployment(
            name="semantic-extraction",
            schedules=[CronSchedule(cron="0 18 * * 0", timezone=LA)],
        ),
        weekly_report_flow.to_deployment(
            name="weekly-report",
            schedules=[CronSchedule(cron="0 20 * * 0", timezone=LA)],
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())

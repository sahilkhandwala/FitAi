"""
Register all Prefect flow schedules.
Run once after Prefect server is started:
  python deployment/deploy_flows.py
"""

import subprocess
import sys

APP_DIR = "/opt/nutrition-bot"
VENV_PYTHON = f"{APP_DIR}/venv/bin/python"
PREFECT = f"{APP_DIR}/venv/bin/prefect"

# Set Prefect API URL to local server
import os
os.environ.setdefault("PREFECT_API_URL", "http://127.0.0.1:4200/api")

from flows.morning_report import morning_report_flow
from flows.alerts import lunch_alert_flow, dinner_alert_flow
from flows.daily_summary import daily_summary_flow
from flows.semantic_extraction import semantic_extraction_flow
from flows.weekly_report import weekly_report_flow

from prefect.client.schemas.schedules import CronSchedule
from prefect import serve

# Deploy all flows with schedules (America/Los_Angeles)
deployments = [
    morning_report_flow.to_deployment(
        name="morning-report",
        schedules=[CronSchedule(cron="30 10 * * *", timezone="America/Los_Angeles")],
    ),
    lunch_alert_flow.to_deployment(
        name="lunch-alert",
        schedules=[CronSchedule(cron="0 15 * * *", timezone="America/Los_Angeles")],
    ),
    dinner_alert_flow.to_deployment(
        name="dinner-alert",
        schedules=[CronSchedule(cron="30 22 * * *", timezone="America/Los_Angeles")],
    ),
    daily_summary_flow.to_deployment(
        name="daily-summary",
        schedules=[CronSchedule(cron="30 23 * * *", timezone="America/Los_Angeles")],
    ),
    semantic_extraction_flow.to_deployment(
        name="semantic-extraction",
        schedules=[CronSchedule(cron="0 18 * * 0", timezone="America/Los_Angeles")],
    ),
    weekly_report_flow.to_deployment(
        name="weekly-report",
        schedules=[CronSchedule(cron="0 20 * * 0", timezone="America/Los_Angeles")],
    ),
]

if __name__ == "__main__":
    import asyncio
    from prefect.deployments import Deployment

    async def deploy_all():
        for d in deployments:
            result = await d.apply()
            print(f"Deployed: {result.name}")

    asyncio.run(deploy_all())
    print("\nAll flows deployed. Run 'prefect deployment ls' to verify.")

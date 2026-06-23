"""
Morning report flow — runs at 10:30am LA time daily (scheduled via Prefect deploy).

Steps:
1. Fetch Fitbit data (steps + sleep) for yesterday
2. Fetch current weather for LA via Open-Meteo
3. Build the user message string
4. Call Claude Haiku to produce the morning message
5. Send via Telegram
"""

import logging
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from prefect import flow, task, get_run_logger
from prefect.exceptions import MissingContextError


def _get_logger():
    try:
        return get_run_logger()
    except MissingContextError:
        return logging.getLogger(__name__)

from config import (
    ANTHROPIC_MODEL_FAST,
    DISKCACHE_DIR,
    FITBIT_CLIENT_ID,
    FITBIT_CLIENT_SECRET,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEATHER_LAT,
    WEATHER_LON,
    WEATHER_LOCATION_NAME,
)

LA = ZoneInfo("America/Los_Angeles")

# WMO weather code → human-readable label (subset)
_WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight showers",
    81: "Moderate showers",
    82: "Violent showers",
    95: "Thunderstorm",
    99: "Thunderstorm w/ hail",
}

_RAIN_CODES = {51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 99}


def _on_flow_failure(flow, flow_run, state):
    """Send Telegram alert when flow fails."""
    text = f"⚠️ morning_report_flow failed: {state.message}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception:
        pass


@task
def fetch_fitbit_data(date_str: str) -> dict:
    """
    Fetch Fitbit steps + sleep for the given date using a cached OAuth2 token.
    Token is stored in diskcache under key 'fitbit_token'.
    Returns dict with keys: steps, sleep_minutes.
    """
    import diskcache

    logger = _get_logger()

    cache = diskcache.Cache(DISKCACHE_DIR)
    token_data = cache.get("fitbit_token")
    if not token_data:
        logger.warning("No Fitbit token in cache — returning zero data")
        return {"steps": 0, "sleep_minutes": 0}

    access_token = token_data.get("access_token", "")
    headers = {"Authorization": f"Bearer {access_token}"}

    # Steps
    steps = 0
    try:
        resp = requests.get(
            f"https://api.fitbit.com/1/user/-/activities/steps/date/{date_str}/1d.json",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        steps_list = data.get("activities-steps", [])
        if steps_list:
            steps = int(steps_list[0].get("value", 0))
    except Exception as e:
        logger.warning(f"Fitbit steps fetch failed: {e}")

    # Sleep
    sleep_minutes = 0
    try:
        resp = requests.get(
            f"https://api.fitbit.com/1.2/user/-/sleep/date/{date_str}.json",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        sleep_minutes = data.get("sleep", {}).get("summary", {}).get("totalTimeInBed", 0)
    except Exception as e:
        logger.warning(f"Fitbit sleep fetch failed: {e}")

    return {"steps": steps, "sleep_minutes": sleep_minutes}


@task
def fetch_weather() -> dict:
    """
    Fetch current weather for LA from Open-Meteo.
    Returns dict with keys: temp_f, condition, rain_expected.
    """
    import openmeteo_requests
    import requests_cache
    from retry_requests import retry

    logger = _get_logger()

    try:
        cache_session = requests_cache.CachedSession(".cache", expire_after=1800)
        retry_session = retry(cache_session, retries=3, backoff_factor=0.3)
        client = openmeteo_requests.Client(session=retry_session)

        params = {
            "latitude": WEATHER_LAT,
            "longitude": WEATHER_LON,
            "current": ["temperature_2m", "weathercode"],
            "temperature_unit": "fahrenheit",
            "timezone": "America/Los_Angeles",
        }
        responses = client.weather_api(
            "https://api.open-meteo.com/v1/forecast", params=params
        )
        response = responses[0]
        current = response.Current()
        temp_f = current.Variables(0).Value()
        weathercode = int(current.Variables(1).Value())
        condition = _WMO_CODES.get(weathercode, "Unknown")
        rain_expected = weathercode in _RAIN_CODES
        return {"temp_f": temp_f, "condition": condition, "rain_expected": rain_expected}
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return {"temp_f": 70.0, "condition": "Unknown", "rain_expected": False}


@task
def build_morning_message(fitbit_data: dict, weather_data: dict) -> str:
    """
    Call Claude Haiku with the morning_report system prompt and the
    assembled user message. Returns the model's text response.
    """
    from pathlib import Path

    logger = _get_logger()

    # Load system prompt
    prompt_path = Path(__file__).parent.parent / "prompts" / "morning_report.txt"
    system_prompt = prompt_path.read_text()

    # Compute yesterday in LA time
    now_la = datetime.now(LA)
    yesterday = (now_la - timedelta(days=1)).date()

    steps = fitbit_data.get("steps", 0)
    sleep_minutes = fitbit_data.get("sleep_minutes", 0)
    sleep_hrs = sleep_minutes / 60.0

    temp_f = weather_data.get("temp_f", 70.0)
    condition = weather_data.get("condition", "Unknown")
    rain_expected = weather_data.get("rain_expected", False)

    # Alternate gita/tech day by day-of-year parity
    day_type = "gita" if now_la.timetuple().tm_yday % 2 == 0 else "tech"

    user_message = (
        f"steps_yesterday: {steps}\n"
        f"step_goal: 10000\n"
        f"sleep_hrs: {sleep_hrs:.1f}\n"
        f"location: {WEATHER_LOCATION_NAME}\n"
        f"temp_f: {temp_f:.1f}\n"
        f"weather_condition: {condition}\n"
        f"rain_expected: {'true' if rain_expected else 'false'}\n"
        f"rain_window: {'morning' if rain_expected else 'none'}\n"
        f"day_type: {day_type}\n"
    )

    llm = ChatAnthropic(model=ANTHROPIC_MODEL_FAST, max_tokens=512)
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ])

    content = response.content
    logger.info("Claude Haiku morning message generated")
    return content


@task
def send_telegram(text: str) -> None:
    """Send a message to the configured Telegram chat."""
    logger = _get_logger()
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=10,
    )
    resp.raise_for_status()
    logger.info("Morning report sent via Telegram")


@flow(name="morning_report", retries=2, retry_delay_seconds=60, on_failure=[_on_flow_failure])
def morning_report_flow():
    """10:30am daily: Fitbit + weather → Haiku → Telegram."""
    logger = _get_logger()

    now_la = datetime.now(LA)
    yesterday_str = (now_la - timedelta(days=1)).strftime("%Y-%m-%d")

    fitbit_data = fetch_fitbit_data(yesterday_str)
    weather_data = fetch_weather()
    message = build_morning_message(fitbit_data, weather_data)
    send_telegram(message)

    logger.info("morning_report_flow completed")

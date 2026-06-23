# config.py

## Summary
Central configuration module. Reads all environment variables (via python-dotenv), exposes typed constants for the entire project. Telegram, Anthropic, Fitbit, weather, and path settings all live here. Uses zoneinfo for timezone. Called at import time by most modules.

## Functions
(none)

## Non-function code
- TZ — ZoneInfo("America/Los_Angeles")
- BASE_DIR — Path to project root
- KNOWLEDGE_BASE_DIR, SQLITE_DB_PATH, DISKCACHE_DIR, TRACES_DIR — file paths from env or defaults
- TELEGRAM_BOT_TOKEN — required env var
- TELEGRAM_CHAT_ID — required env var, cast to int
- ANTHROPIC_API_KEY — required env var
- ANTHROPIC_MODEL_HEAVY, ANTHROPIC_MODEL_MID, ANTHROPIC_MODEL_FAST — model name strings with defaults
- FITBIT_CLIENT_ID, FITBIT_CLIENT_SECRET — optional env vars
- WEATHER_LAT, WEATHER_LON, WEATHER_LOCATION_NAME — Open-Meteo coordinates
- UPTIME_KUMA_PUSH_URL — optional push URL, empty string default
- DEFAULT_STEP_GOAL, DEFAULT_SLEEP_GOAL_HRS — fallback goal values

## Imports
- os, pathlib.Path, zoneinfo.ZoneInfo, dotenv.load_dotenv

## Imported by
- bot/handlers/meal.py — TELEGRAM_CHAT_ID
- bot/handlers/health.py — TELEGRAM_CHAT_ID
- bot/handlers/commands.py — TELEGRAM_CHAT_ID
- bot/main.py — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, UPTIME_KUMA_PUSH_URL
- db/__init__.py — SQLITE_DB_PATH

## Tags
config, env, constants, telegram, anthropic

## Node path
config.py

# config.py

## Summary
Application-wide configuration for FitAi. Loads environment variables via dotenv and exposes all constants used across the project: timezone, paths (SQLite DB, knowledge base, cache, traces), Telegram credentials, Anthropic model strings, Fitbit API keys, weather coordinates, and Uptime Kuma push URL.

## Functions
No functions — pure constants module.

## Non-function code
- `TZ` — ZoneInfo("America/Los_Angeles"), project-wide timezone
- `BASE_DIR` — Path of the project root
- `KNOWLEDGE_BASE_DIR` — Path to knowledge_base/ directory (env-overridable)
- `SQLITE_DB_PATH` — SQLite file path (env-overridable, default: nutrition.db)
- `DISKCACHE_DIR` — diskcache directory path
- `TRACES_DIR` — Monocle traces output directory
- `TELEGRAM_BOT_TOKEN` — required env var
- `TELEGRAM_CHAT_ID` — required env var, cast to int
- `ANTHROPIC_API_KEY` — required env var
- `ANTHROPIC_MODEL_HEAVY` — defaults to "claude-opus-4-8"
- `ANTHROPIC_MODEL_MID` — defaults to "claude-sonnet-4-6"
- `ANTHROPIC_MODEL_FAST` — defaults to "claude-haiku-4-5-20251001"
- `FITBIT_CLIENT_ID`, `FITBIT_CLIENT_SECRET` — optional
- `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_LOCATION_NAME` — Open-Meteo coords
- `UPTIME_KUMA_PUSH_URL` — optional
- `DEFAULT_STEP_GOAL`, `DEFAULT_SLEEP_GOAL_HRS` — fallback goals

## Imports
- os, pathlib.Path, zoneinfo.ZoneInfo, dotenv.load_dotenv

## Imported by
- db/queries.py — for TZ (timezone) via its own ZoneInfo call
- bot/agents/tool_registry.py — for KNOWLEDGE_BASE_DIR, TELEGRAM_CHAT_ID
- bot/agents/base_agent.py — ChatAnthropic uses model strings from here indirectly
- bot/agents/agent_loader.py — for ANTHROPIC_MODEL_HEAVY/MID/FAST

## Tags
config, env, paths, models, telegram, anthropic

## Node path
config.py

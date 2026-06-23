# commands.py

## Summary
Telegram command handlers and general text message routing. Contains two pure parsing helpers (fully testable without Telegram) and async handler functions for /profile, /help, /addfood, profile updates, and catch-all text messages. Uses regex keyword matching (not LLM) for profile field parsing. Agent and DB calls are stubbed for Wave 2.

## Functions
- parse_profile_update_command(text) — pure: regex-matches natural language profile updates; returns dict of {field: value} pairs with correct types (calorie_target=int, step_goal=int, weight_kg=float, sleep_goal_hrs=float, activity_level=str, diet_type=str); returns {} if nothing matches
- is_skip_comparison_message(text) — pure: returns True iff text.strip().lower() == "skip comparison"
- handle_profile_command(update, context) — async: displays user_profile + latest health_profile (stubbed)
- handle_profile_update(update, context) — async: parses text with parse_profile_update_command, applies DB updates (stubbed)
- handle_addfood_command(update, context) — async: parses /addfood <name>, upserts indian_foods entry (stubbed)
- handle_help_command(update, context) — async: sends hardcoded help text listing commands and capabilities
- handle_text_message(update, context) — async: checks for "skip comparison", checks for paused LangGraph interrupt (stubbed), routes to OrchestratorAgent (stubbed)

## Non-function code
- `_PROFILE_PATTERNS` — list of (compiled regex, field name, cast type) for parse_profile_update_command
- `from __future__ import annotations` + `TYPE_CHECKING` guard — keeps telegram imports lazy

## Imports
- re — regex for parse_profile_update_command
- config.TELEGRAM_CHAT_ID — single-user auth guard
- telegram (TYPE_CHECKING) — Update (lazy)
- telegram.ext (TYPE_CHECKING) — ContextTypes (lazy)

## Imported by
- tests/unit/test_commands.py — tests pure helpers
- bot/main.py — registers all command and text handlers

## Tags
telegram, handler, commands, parsing, routing, profile

## Node path
bot/handlers/commands.py

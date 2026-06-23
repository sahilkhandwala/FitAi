# meal.py

## Summary
Telegram photo handler implementing media group buffering for multi-photo albums. Provides three pure helper functions for TTLCache-based buffering (testable without Telegram), plus async handler functions for routing photo messages to OrchestratorAgent → MealAnalyzerAgent. Agent call stubs are in place; actual agent invocation is a TODO for Wave 2.

## Functions
- buffer_photo(media_group_id, file_id, cache) — appends file_id to cache["media_group:{id}"] list, creating the list on first call
- get_buffered_photos(media_group_id, cache) — returns buffered file_ids for a group, or [] if not present
- is_new_media_group(media_group_id, cache) — returns True if "media_group:{id}" is not yet in cache
- handle_photo(update, context) — async Telegram handler: rejects non-TELEGRAM_CHAT_ID, buffers photos in media groups, schedules process_media_group job, or sends meal-type keyboard for single photos
- process_media_group(context) — async job scheduled 2.1s after first group photo; reads buffered photos and sends meal-type inline keyboard
- handle_meal_type_callback(update, context) — async callback handler for Breakfast/Lunch/Dinner/Snack buttons; retrieves pending photos and stubs OrchestratorAgent call

## Non-function code
- `media_buffer: TTLCache = TTLCache(maxsize=100, ttl=2)` — module-level shared buffer, 2s TTL per spec
- `MEAL_TYPE_KEYBOARD_BUTTONS = ["Breakfast", "Lunch", "Dinner", "Snack"]` — inline keyboard labels
- `from __future__ import annotations` + `TYPE_CHECKING` guard — keeps `telegram` imports lazy so pure helpers are importable without python-telegram-bot installed

## Imports
- cachetools.TTLCache — media group buffering
- config.TELEGRAM_CHAT_ID — single-user auth guard
- telegram (TYPE_CHECKING) — Update, InlineKeyboardButton, InlineKeyboardMarkup (lazy)
- telegram.ext (TYPE_CHECKING) — ContextTypes (lazy)

## Imported by
- tests/unit/test_meal_handler.py — tests pure helpers
- tests/unit/test_media_group_buffer.py — tests TTLCache key format and grouping
- bot/main.py — registers handle_photo and handle_meal_type_callback

## Tags
telegram, handler, media-group, photo, cachetools, routing

## Node path
bot/handlers/meal.py

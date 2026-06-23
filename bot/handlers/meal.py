"""
Telegram handler for photo messages (single photos and media group albums).

Routing only — no LLM calls, no DB access.

Media group buffering:
  Telegram sends album photos as separate Update messages that all share a
  media_group_id. We buffer file_ids in a TTLCache(ttl=2s) keyed by
  "media_group:{id}". The first photo in a group schedules a job to fire at
  2.1s; when the job runs it reads all buffered photos and sends the meal-type
  inline keyboard.

NOTE: The TTL-vs-job-delay gap is a latent timing risk. The TTLCache key
expires 2s after creation; the job fires at 2.1s, so get_buffered_photos()
may return [] if the cache expires before the job runs. In production, raise
the TTL to 5-10s while keeping the job delay at 2.1s. Tracked as a known
design risk — values match the task spec.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cachetools import TTLCache

from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

# Module-level shared media buffer — 2s TTL per the spec.
# Import this directly in tests to verify behavior.
media_buffer: TTLCache = TTLCache(maxsize=100, ttl=2)

# Inline keyboard definition for meal type selection
MEAL_TYPE_KEYBOARD_BUTTONS = ["Breakfast", "Lunch", "Dinner", "Snack"]


# ---------------------------------------------------------------------------
# Pure helper functions — testable without Telegram context
# ---------------------------------------------------------------------------

def buffer_photo(media_group_id: str, file_id: str, cache: TTLCache) -> None:
    """Add file_id to the buffer list for this media_group_id."""
    key = f"media_group:{media_group_id}"
    if key not in cache:
        cache[key] = []
    cache[key].append(file_id)


def get_buffered_photos(media_group_id: str, cache: TTLCache) -> list:
    """Return all buffered file_ids for this media_group_id (empty list if none)."""
    return cache.get(f"media_group:{media_group_id}", [])


def is_new_media_group(media_group_id: str, cache: TTLCache) -> bool:
    """Return True if this media_group_id has not been buffered yet."""
    return f"media_group:{media_group_id}" not in cache


# ---------------------------------------------------------------------------
# Handler functions — require Telegram context (imports deferred)
# ---------------------------------------------------------------------------

async def handle_photo(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """
    Called for every photo message. Handles single photos and albums (media groups).

    1. Reject if chat_id != TELEGRAM_CHAT_ID
    2. If media group:
       a. Capture is_new BEFORE buffering
       b. Buffer the file_id
       c. If first photo in group: schedule process_media_group at 2.1s
    3. If single photo:
       - Store file_id in context.user_data['pending_photos']
       - Send meal-type inline keyboard
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    photo = update.message.photo[-1]  # largest available size
    file_id = photo.file_id
    media_group_id = update.message.media_group_id

    if media_group_id:
        is_new = is_new_media_group(media_group_id, media_buffer)
        buffer_photo(media_group_id, file_id, media_buffer)
        if is_new:
            context.job_queue.run_once(
                process_media_group,
                2.1,
                data=media_group_id,
            )
    else:
        # Single photo — send meal type keyboard immediately
        context.user_data["pending_photos"] = [file_id]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data=f"meal_type:{label.lower()}")]
            for label in MEAL_TYPE_KEYBOARD_BUTTONS
        ])
        await update.message.reply_text(
            "What meal is this?",
            reply_markup=keyboard,
        )


async def process_media_group(context: "ContextTypes.DEFAULT_TYPE") -> None:
    """
    Job scheduled 2.1s after the first photo in a media group arrives.
    Reads all buffered photos for the group and sends the meal-type keyboard.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ContextTypes  # noqa: F401 — ensures import at runtime

    media_group_id: str = context.job.data
    file_ids = get_buffered_photos(media_group_id, media_buffer)

    if not file_ids:
        # Cache already expired — log and bail (known TTL race risk)
        import logging
        logging.getLogger(__name__).warning(
            "process_media_group: cache miss for group %s (TTL expired before job ran)",
            media_group_id,
        )
        return

    context.bot_data.setdefault("pending_photos", {})
    context.bot_data["pending_photos"][media_group_id] = file_ids

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"meal_type:{label.lower()}|{media_group_id}")]
        for label in MEAL_TYPE_KEYBOARD_BUTTONS
    ])
    await context.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"What meal is this? ({len(file_ids)} photo(s))",
        reply_markup=keyboard,
    )


async def handle_meal_type_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    Called when user taps [Breakfast] [Lunch] [Dinner] [Snack] inline keyboard.
    Routes to OrchestratorAgent → MealAnalyzerAgent with pending photos + meal_type.
    """
    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    data = query.data  # "meal_type:<type>" or "meal_type:<type>|<media_group_id>"

    if "|" in data:
        _, rest = data.split(":", 1)
        meal_type, media_group_id = rest.split("|", 1)
        file_ids = context.bot_data.get("pending_photos", {}).pop(media_group_id, [])
    else:
        meal_type = data.split(":", 1)[1]
        media_group_id = None
        file_ids = context.user_data.pop("pending_photos", [])

    if not file_ids:
        await query.edit_message_text("Sorry, I lost track of those photos — please send them again.")
        return

    await query.edit_message_text(f"Got it! Analyzing your {meal_type}...")

    # TODO: call OrchestratorAgent → MealAnalyzerAgent
    # agent_input = AgentState(
    #     input_type="photo",
    #     telegram_chat_id=TELEGRAM_CHAT_ID,
    #     messages=[],
    #     media_group_id=media_group_id,
    #     photos=file_ids,
    #     analysis_result=None,
    #     next_agent="MealAnalyzerAgent",
    # )
    # result = await orchestrator_agent.invoke(agent_input)
    # After save: trigger PatternDetectorAgent

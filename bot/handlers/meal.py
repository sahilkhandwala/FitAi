"""
Telegram handler for photo messages (single photos and media group albums).

Routing only except for photo download — no LLM calls happen here beyond
dispatching to MealAnalyzerAgent and PatternDetectorAgent.

Media group buffering:
  Telegram sends album photos as separate Update messages that all share a
  media_group_id. We buffer file_ids in a TTLCache(ttl=2s) keyed by
  "media_group:{id}". The first photo in a group schedules a job to fire at
  2.1s; when the job runs it reads all buffered photos and processes as one meal.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import TYPE_CHECKING

from cachetools import TTLCache
from langchain_core.messages import HumanMessage

from bot.cache import clear_paused_agent, set_paused_agent
from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

media_buffer: TTLCache = TTLCache(maxsize=100, ttl=2)
MEAL_TYPE_KEYBOARD_BUTTONS = ["Breakfast", "Lunch", "Dinner", "Snack"]


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def buffer_photo(media_group_id: str, file_id: str, cache: TTLCache) -> None:
    key = f"media_group:{media_group_id}"
    if key not in cache:
        cache[key] = []
    cache[key].append(file_id)


def get_buffered_photos(media_group_id: str, cache: TTLCache) -> list:
    return cache.get(f"media_group:{media_group_id}", [])


def is_new_media_group(media_group_id: str, cache: TTLCache) -> bool:
    return f"media_group:{media_group_id}" not in cache


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_photo(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id
    media_group_id = update.message.media_group_id

    if media_group_id:
        is_new = is_new_media_group(media_group_id, media_buffer)
        buffer_photo(media_group_id, file_id, media_buffer)
        if is_new:
            context.job_queue.run_once(process_media_group, 2.1, data=media_group_id)
    else:
        context.user_data["pending_photos"] = [file_id]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data=f"meal_type:{label.lower()}")]
            for label in MEAL_TYPE_KEYBOARD_BUTTONS
        ])
        await update.message.reply_text("What meal is this?", reply_markup=keyboard)


async def process_media_group(context: "ContextTypes.DEFAULT_TYPE") -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    media_group_id: str = context.job.data
    file_ids = get_buffered_photos(media_group_id, media_buffer)

    if not file_ids:
        logger.warning("process_media_group: cache miss for group %s", media_group_id)
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
    User tapped a meal type button. Downloads photos, invokes MealAnalyzerAgent,
    then PatternDetectorAgent. Handles GraphInterrupt for web search permission.
    """
    from langgraph.errors import GraphInterrupt
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    data = query.data

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

    await query.edit_message_text(f"Got it! Analyzing your {meal_type}... 🔍")

    # Download all photos from Telegram
    photo_contents = []
    for file_id in file_ids:
        tg_file = await context.bot.get_file(file_id)
        raw: bytearray = await tg_file.download_as_bytearray()
        b64 = base64.b64encode(bytes(raw)).decode()
        photo_contents.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })

    photo_contents.append({
        "type": "text",
        "text": f"Please analyze these {len(file_ids)} food photo(s). This is a {meal_type}.",
    })

    from bot.agents.agent_loader import AGENT_REGISTRY
    agent = AGENT_REGISTRY.get("photo")
    if agent is None:
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Agent not ready yet — please try again in a moment.")
        return

    state = {
        "input_type": "photo",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content=photo_contents)],
        "media_group_id": media_group_id,
        "photos": file_ids,
        "analysis_result": None,
        "next_agent": None,
    }

    thread_id = f"meal-{TELEGRAM_CHAT_ID}"
    loop = asyncio.get_event_loop()

    try:
        await loop.run_in_executor(
            None, lambda: agent.invoke(state, thread_id=thread_id)
        )
        clear_paused_agent()
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=f"Got it! Your {meal_type} has been logged 📷",
        )
        # Fire PatternDetectorAgent in background (non-blocking)
        asyncio.ensure_future(_run_pattern_detector(loop))

    except GraphInterrupt as exc:
        interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Can I search the web?"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Yes, go ahead 🔍", callback_data="websearch:yes"),
            InlineKeyboardButton("No thanks", callback_data="websearch:no"),
        ]])
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=interrupt_msg, reply_markup=keyboard
        )
        set_paused_agent("photo")


async def _run_pattern_detector(loop: asyncio.AbstractEventLoop) -> None:
    """Invoke PatternDetectorAgent after a meal is saved. Fire-and-forget."""
    from bot.agents.agent_loader import AGENT_REGISTRY

    agent = AGENT_REGISTRY.get("pattern_detector")
    if agent is None:
        return
    state = {
        "input_type": "cron",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content="Check today's meal logs for patterns.")],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }
    try:
        await loop.run_in_executor(None, lambda: agent.invoke(state))
    except Exception as e:
        logger.warning("PatternDetectorAgent failed: %s", e)

"""
User onboarding flow — runs on first message when user_profile row doesn't exist.

Uses diskcache key 'onboarding_complete' to track whether setup is done.
Multi-step inline keyboard conversation:
  Step 1: diet type
  Step 2: activity level
  Step 3: calorie target

On completion: saves to user_profile, sets onboarding_complete.
One-time lab prompt: if profile lacks health data, sends a one-time tip.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import TELEGRAM_CHAT_ID
from bot.cache import (
    get_app_cache,
    is_onboarding_complete,
    set_onboarding_complete,
    has_sent_onboarding_prompt,
    set_onboarding_prompt_sent,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_KEY_ONBOARDING_STEP = "onboarding_step"
_KEY_ONBOARDING_ANSWERS = "onboarding_answers"


def is_onboarding_needed(session: "Session") -> bool:
    """Return True if onboarding hasn't been completed and no user_profile row exists."""
    if is_onboarding_complete():
        return False
    from db import queries
    return queries.get_user_profile(session) is None


def save_onboarding_answers(session: "Session", answers: dict) -> None:
    """Save collected onboarding answers to user_profile and mark onboarding complete."""
    from db import queries
    queries.upsert_user_profile(session, **{k: v for k, v in answers.items() if v is not None})
    set_onboarding_complete()


async def start_onboarding(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """Send first onboarding question (diet type)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    cache = get_app_cache()
    cache.set(_KEY_ONBOARDING_STEP, 1)
    cache.set(_KEY_ONBOARDING_ANSWERS, {})

    # callback_data key matches the UserProfile column name: diet_type
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🥩 Omnivore", callback_data="onboard:diet_type:omnivore"),
        InlineKeyboardButton("🥦 Vegetarian", callback_data="onboard:diet_type:vegetarian"),
        InlineKeyboardButton("🌱 Vegan", callback_data="onboard:diet_type:vegan"),
    ]])
    await update.message.reply_text(
        "Hey Sahil! 👋 Let me personalise your experience with a few quick questions.\n\n"
        "What's your diet type?",
        reply_markup=keyboard,
    )


async def handle_onboarding_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    Handle inline keyboard taps during onboarding.
    Callback data format: "onboard:<step_key>:<value>"
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.agents.tool_registry import _get_session

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    # Parse callback data: "onboard:<step_key>:<value>"
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, step_key, value = parts

    cache = get_app_cache()
    answers: dict = cache.get(_KEY_ONBOARDING_ANSWERS, {})
    answers[step_key] = value
    cache.set(_KEY_ONBOARDING_ANSWERS, answers)

    step = cache.get(_KEY_ONBOARDING_STEP, 1)

    if step == 1:
        # Received diet type → ask activity level
        cache.set(_KEY_ONBOARDING_STEP, 2)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🪑 Sedentary", callback_data="onboard:activity_level:sedentary"),
            InlineKeyboardButton("🚶 Moderate", callback_data="onboard:activity_level:moderate"),
            InlineKeyboardButton("🏃 Active", callback_data="onboard:activity_level:active"),
        ]])
        await query.edit_message_text(
            "What's your typical activity level?", reply_markup=keyboard
        )

    elif step == 2:
        # Received activity level → ask calorie target
        cache.set(_KEY_ONBOARDING_STEP, 3)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("1,600 kcal", callback_data="onboard:calorie_target:1600"),
            InlineKeyboardButton("1,800 kcal", callback_data="onboard:calorie_target:1800"),
            InlineKeyboardButton("2,000 kcal", callback_data="onboard:calorie_target:2000"),
            InlineKeyboardButton("Skip for now", callback_data="onboard:calorie_target:skip"),
        ]])
        await query.edit_message_text(
            "Last one — what's your daily calorie target?", reply_markup=keyboard
        )

    elif step == 3:
        # Received calorie target → save and complete
        if value == "skip":
            answers.pop("calorie_target", None)
        else:
            answers["calorie_target"] = int(value)

        answers.setdefault("name", "Sahil")

        try:
            session = _get_session()
        except RuntimeError:
            await query.edit_message_text("Setup error — please restart the bot and try again.")
            return

        save_onboarding_answers(session, answers)
        cache.delete(_KEY_ONBOARDING_STEP)
        cache.delete(_KEY_ONBOARDING_ANSWERS)

        await query.edit_message_text(
            "You're all set! 🎉 I'm ready to be your personal nutrition bot.\n\n"
            "📷 Send me a photo of your next meal to get started!\n"
            "📋 Tip: send me your latest lab report PDF and I'll personalise everything "
            "to your actual A1C and cholesterol values."
        )
        set_onboarding_prompt_sent()


async def maybe_send_onboarding_prompt(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE", session: "Session"
) -> bool:
    """
    If onboarding is complete but no lab report has been uploaded,
    append a one-time tip. Returns True if the tip was sent (caller should
    not process the message further in that case — the user may be mid-flow).
    """
    if has_sent_onboarding_prompt():
        return False
    from db import queries
    if queries.get_latest_health_profile(session) is not None:
        return False
    await update.message.reply_text(
        "📋 Tip: send me your latest lab report PDF and I'll personalise "
        "everything to your actual A1C and cholesterol values."
    )
    set_onboarding_prompt_sent()
    return False  # don't block further processing

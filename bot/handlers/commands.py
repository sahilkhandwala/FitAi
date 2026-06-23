"""
Telegram command handlers and text message routing.

Pure parsing helpers (parse_profile_update_command, is_skip_comparison_message)
are importable without a Telegram context and are tested independently.

Handler functions are routing only — no LLM calls, no DB writes.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


# ---------------------------------------------------------------------------
# Pure helper functions — testable without Telegram context
# ---------------------------------------------------------------------------

# Patterns: (regex, output_field, cast_fn)
# Ordered from most-specific to least-specific within each field.
_PROFILE_PATTERNS: list[tuple[re.Pattern, str, type]] = [
    (re.compile(r"\bcalorie[s]?\s+target\s+to\s+(\d+)", re.IGNORECASE), "calorie_target", int),
    (re.compile(r"\bweight\s+to\s+([\d.]+)", re.IGNORECASE), "weight_kg", float),
    (re.compile(r"\bactivity\s+level\s+to\s+(\w+)", re.IGNORECASE), "activity_level", str),
    (re.compile(r"\bstep\s+goal\s+to\s+(\d+)", re.IGNORECASE), "step_goal", int),
    (re.compile(r"\bsleep\s+goal\s+to\s+([\d.]+)", re.IGNORECASE), "sleep_goal_hrs", float),
    (re.compile(r"\bdiet\s+type\s+to\s+(\w+)", re.IGNORECASE), "diet_type", str),
]


def parse_profile_update_command(text: str) -> dict:
    """
    Parse a natural language profile update into a dict of field→value pairs.

    Uses keyword matching — not an LLM. Returns {} if nothing parseable.

    Supported fields:
      calorie_target (int), weight_kg (float), activity_level (str),
      step_goal (int), sleep_goal_hrs (float), diet_type (str)

    Examples:
      "change my calorie target to 2000"  → {"calorie_target": 2000}
      "update my weight to 79"            → {"weight_kg": 79.0}
      "change activity level to active"   → {"activity_level": "active"}
    """
    result: dict = {}
    for pattern, field, cast in _PROFILE_PATTERNS:
        match = pattern.search(text)
        if match:
            result[field] = cast(match.group(1))
    return result


def is_skip_comparison_message(text: str) -> bool:
    """Return True iff the message is exactly 'skip comparison' (case-insensitive)."""
    return text.strip().lower() == "skip comparison"


# ---------------------------------------------------------------------------
# Handler functions — require Telegram context
# ---------------------------------------------------------------------------

async def handle_profile_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Display current user_profile + latest health_profile values."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    # TODO: query db/queries.py for user_profile and latest user_health_profile
    # profile = get_user_profile(session)
    # health = get_health_profile(session)
    # await update.message.reply_text(format_profile(profile, health))
    await update.message.reply_text("(Profile display not yet implemented)")


async def handle_profile_update(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Let user update profile fields conversationally."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    text = update.message.text or ""
    updates = parse_profile_update_command(text)

    if not updates:
        await update.message.reply_text(
            "I didn't catch that. Try something like: "
            '"change my calorie target to 2000" or "update my weight to 79"'
        )
        return

    # TODO: apply updates via db/queries.py
    # update_user_profile(session, **updates)
    field_list = ", ".join(f"{k}={v}" for k, v in updates.items())
    await update.message.reply_text(f"Updated: {field_list}")


async def handle_addfood_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    Parse /addfood <name> and add/update entry in indian_foods table.

    Usage: /addfood Dal Makhani
    """
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /addfood <food name>\nExample: /addfood Dal Makhani"
        )
        return

    food_name = " ".join(args)

    # TODO: add/update indian_foods entry via db/queries.py
    # upsert_indian_food(session, name=food_name)
    await update.message.reply_text(
        f'Added "{food_name}" to the Indian foods database.'
    )


async def handle_help_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Send the help message listing available commands."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    help_text = (
        "Here's what I can do:\n\n"
        "📷 Send a photo (or album) → log a meal\n"
        "📄 Send a PDF → upload a lab report or research article\n\n"
        "Commands:\n"
        "/profile — view your current profile and latest lab values\n"
        "/addfood <name> — add a food to the Indian foods database\n"
        "/help — show this message\n\n"
        "You can also just chat with me — ask about your nutrition, "
        "health patterns, or what you should eat today."
    )
    await update.message.reply_text(help_text)


async def handle_text_message(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    Catch-all for text messages (not commands, not photos, not PDFs).

    1. If 'skip comparison' → set context flag and acknowledge
    2. Check if a LangGraph graph is paused (interrupt) for this chat → resume it
    3. Otherwise route to OrchestratorAgent
    """
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    text = update.message.text or ""

    if is_skip_comparison_message(text):
        context.user_data["skip_comparison"] = True
        await update.message.reply_text("Got it — skipping the comparison this time.")
        return

    # TODO: check for paused LangGraph graph (interrupt resume)
    # thread_config = {"configurable": {"thread_id": str(TELEGRAM_CHAT_ID)}}
    # if graph_has_pending_interrupt(thread_config):
    #     await orchestrator_graph.ainvoke(
    #         Command(resume=text), config=thread_config
    #     )
    #     return

    # TODO: route to OrchestratorAgent for general questions / health insights
    # agent_input = AgentState(
    #     input_type="command",
    #     telegram_chat_id=TELEGRAM_CHAT_ID,
    #     messages=[{"role": "user", "content": text}],
    #     media_group_id=None,
    #     photos=[],
    #     analysis_result=None,
    #     next_agent=None,
    # )
    # await orchestrator_agent.invoke(agent_input)
    await update.message.reply_text("(OrchestratorAgent not yet wired up)")

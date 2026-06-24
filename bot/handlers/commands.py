"""
Telegram command handlers and text message routing.

handle_text_message:
  1. Check diskcache for a paused agent — resume if found
  2. "skip comparison" text → update DB flag + acknowledge
  3. Route to OrchestratorAgent → if it calls route_to_agent("HealthInsightsAgent"),
     invoke HealthInsightsAgent with checkpointer thread_id

handle_profile_command: query and display user_profile + latest health_profile
handle_profile_update: parse natural language update, write to DB
handle_addfood_command: parse /addfood args, upsert to indian_foods table
handle_help_command: send command list
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from bot.cache import clear_paused_agent, get_paused_agent, set_paused_agent
from config import TELEGRAM_CHAT_ID

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helper functions — testable without Telegram context
# ---------------------------------------------------------------------------

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


def _format_profile(profile_row, health_row) -> str:
    """Format user_profile + health_profile into a readable Telegram message."""
    lines = ["📋 *Your Profile*\n"]

    if profile_row:
        lines.append(
            f"👤 {profile_row.name or 'Sahil'}, {profile_row.age or '?'} y/o, {profile_row.gender or '?'}\n"
            f"📏 Height: {profile_row.height_cm or '?'}cm  Weight: {profile_row.weight_kg or '?'}kg\n"
            f"🥗 Diet: {profile_row.diet_type or '?'}  Activity: {profile_row.activity_level or '?'}\n"
            f"🎯 Goals: {profile_row.step_goal or 10000} steps/day · {profile_row.sleep_goal_hrs or 7}hrs sleep\n"
            f"📊 Targets: {profile_row.calorie_target or '?'} kcal · "
            f"{profile_row.protein_target_g or '?'}g protein · "
            f"{profile_row.carb_target_g or '?'}g carbs · "
            f"{profile_row.fat_target_g or '?'}g fat\n"
        )
    else:
        lines.append("No user profile set yet. Send /profile update to add details.\n")

    if health_row:
        lines.append(
            f"\n🧪 *Latest Labs* ({health_row.report_date})\n"
            f"A1C: {health_row.a1c}%  LDL: {health_row.ldl} mg/dL  "
            f"HDL: {health_row.hdl} mg/dL  TG: {health_row.triglycerides} mg/dL\n"
            f"BMI: {health_row.bmi}  Meds: {', '.join(health_row.medications or []) or 'none'}"
        )
    else:
        lines.append("\n🧪 No lab report uploaded yet — send a PDF to get personalised guidance.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_profile_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Display current user_profile + latest health_profile values."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    from bot.agents.tool_registry import _get_session
    from db import queries

    try:
        session = _get_session()
    except RuntimeError:
        await update.message.reply_text("Bot still starting up — try again in a moment.")
        return

    profile = queries.get_user_profile(session)
    health = queries.get_latest_health_profile(session)
    await update.message.reply_text(_format_profile(profile, health), parse_mode="Markdown")


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
            "I didn't catch that. Try something like:\n"
            '"change my calorie target to 2000" or "update my weight to 79"'
        )
        return

    from bot.agents.tool_registry import _get_session
    from db import queries

    session = _get_session()
    queries.upsert_user_profile(session, **updates)
    field_list = ", ".join(f"{k} → {v}" for k, v in updates.items())
    await update.message.reply_text(f"Done! Updated: {field_list} 👍")


async def handle_addfood_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Parse /addfood <name> and add/update entry in indian_foods table."""
    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /addfood <food name>\nExample: /addfood Dal Makhani"
        )
        return

    food_name = " ".join(args)

    from bot.agents.tool_registry import _get_session
    from db import queries

    session = _get_session()
    queries.upsert_indian_food(session, name=food_name)
    await update.message.reply_text(f'Added "{food_name}" to the Indian foods database. 🍛')


async def handle_help_command(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
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


async def handle_websearch_callback(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """Handle yes/no tap from web search permission keyboard."""
    from langgraph.types import Command
    from bot.agents.agent_loader import AGENT_REGISTRY

    query = update.callback_query
    await query.answer()

    if query.message.chat_id != TELEGRAM_CHAT_ID:
        return

    choice = query.data.split(":", 1)[1]  # "yes" or "no"
    paused_trigger = get_paused_agent()
    if paused_trigger is None:
        await query.edit_message_text("No active request to resume.")
        return

    agent = AGENT_REGISTRY.get(paused_trigger)
    if agent is None:
        await query.edit_message_text("Agent not available — please try again.")
        clear_paused_agent()
        return

    thread_id = _thread_id_for_trigger(paused_trigger)
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            None,
            lambda: agent.graph.invoke(
                Command(resume=choice),
                config={"configurable": {"thread_id": thread_id}},
            ),
        )
    except Exception as e:
        logger.error("Error resuming agent %s: %s", paused_trigger, e)
    finally:
        clear_paused_agent()

    await query.edit_message_text("Got it! Continuing..." if choice == "yes" else "No problem, skipping web search.")


async def handle_text_message(
    update: "Update", context: "ContextTypes.DEFAULT_TYPE"
) -> None:
    """
    Catch-all for text messages (not commands, not photos, not PDFs).

    1. If a LangGraph graph is paused (interrupt), resume it
    2. "skip comparison" → write DB flag + acknowledge
    3. Route to OrchestratorAgent
    4. If orchestrator routes to HealthInsightsAgent, invoke it
    """
    from langgraph.errors import GraphInterrupt
    from langgraph.types import Command
    from bot.agents.agent_loader import AGENT_REGISTRY
    from bot.agents.tool_registry import AGENT_NAME_TO_TRIGGER
    from bot.handlers.health import extract_routing_from_state

    if update.message.chat_id != TELEGRAM_CHAT_ID:
        return

    # Onboarding check
    from bot.handlers.onboarding import is_onboarding_needed, start_onboarding, maybe_send_onboarding_prompt
    from bot.agents.tool_registry import _get_session
    try:
        session = _get_session()
        if is_onboarding_needed(session):
            await start_onboarding(update, context)
            return
        await maybe_send_onboarding_prompt(update, context, session)
    except RuntimeError:
        pass  # session not ready at startup

    text = update.message.text or ""
    loop = asyncio.get_running_loop()

    # 1. Check for paused agent — resume it
    paused_trigger = get_paused_agent()
    if paused_trigger is not None:
        agent = AGENT_REGISTRY.get(paused_trigger)
        if agent is None:
            clear_paused_agent()
            await update.message.reply_text("Sorry, I lost track of what we were doing — please start again.")
            return
        thread_id = _thread_id_for_trigger(paused_trigger)
        try:
            # Resume interrupted graph directly — bypasses BaseAgent.invoke() which would reset the graph
            await loop.run_in_executor(
                None,
                lambda: agent.graph.invoke(
                    Command(resume=text),
                    config={"configurable": {"thread_id": thread_id}},
                ),
            )
            clear_paused_agent()
        except GraphInterrupt as exc:
            interrupt_msg = exc.interrupts[0].value if exc.interrupts else text
            await update.message.reply_text(interrupt_msg)
        return

    # 2. "skip comparison" special case — write to weekly_reports if a report exists
    if is_skip_comparison_message(text):
        _write_skip_comparison()
        await update.message.reply_text(
            "Got it — I'll skip the recommendation follow-through in this Sunday's report 👍"
        )
        return

    # 3. Route to OrchestratorAgent
    orchestrator = AGENT_REGISTRY.get("text")
    if orchestrator is None:
        await update.message.reply_text("Bot still warming up — try again in a moment.")
        return

    state = {
        "input_type": "text",
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "messages": [HumanMessage(content=text)],
        "media_group_id": None,
        "photos": [],
        "analysis_result": None,
        "next_agent": None,
    }

    try:
        orch_result = await loop.run_in_executor(None, lambda: orchestrator.invoke(state))
    except GraphInterrupt as exc:
        interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Waiting for your response..."
        await update.message.reply_text(interrupt_msg)
        set_paused_agent("text")
        return

    # 4. Check if orchestrator routed to HealthInsightsAgent
    agent_name = extract_routing_from_state(orch_result)
    if agent_name == "HealthInsightsAgent":
        trigger = AGENT_NAME_TO_TRIGGER.get("HealthInsightsAgent", "health_question")
        specialist = AGENT_REGISTRY.get(trigger)
        if specialist is not None:
            thread_id = f"insights-{TELEGRAM_CHAT_ID}"
            try:
                # Fresh invocation via BaseAgent.invoke() — builds config and context injection
                await loop.run_in_executor(
                    None, lambda: specialist.invoke(state, thread_id=thread_id)
                )
            except GraphInterrupt as exc:
                interrupt_msg = exc.interrupts[0].value if exc.interrupts else "Can I search the web?"
                await update.message.reply_text(interrupt_msg)
                set_paused_agent("health_question")


def _thread_id_for_trigger(trigger: str) -> str:
    return {
        "photo": f"meal-{TELEGRAM_CHAT_ID}",
        "lab_report": f"health-extract-{TELEGRAM_CHAT_ID}",
        "health_question": f"insights-{TELEGRAM_CHAT_ID}",
        "text": f"text-{TELEGRAM_CHAT_ID}",
    }.get(trigger, f"{trigger}-{TELEGRAM_CHAT_ID}")


def _write_skip_comparison() -> None:
    """Write skip_comparison=1 to the most recent weekly_reports row, if one exists."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from bot.agents.tool_registry import _get_session
    from db.models import WeeklyReport

    try:
        session = _get_session()
        today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
        # Compute Monday of the current week (LA time)
        week_start = str(today - timedelta(days=today.weekday()))
        row = session.query(WeeklyReport).filter_by(week_start=week_start).first()
        if row is None:
            row = WeeklyReport(week_start=week_start, skip_comparison=1)
            session.add(row)
        else:
            row.skip_comparison = 1
        session.commit()
    except Exception as e:
        logger.warning("Could not write skip_comparison: %s", e)

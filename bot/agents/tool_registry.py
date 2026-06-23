"""
Tool registry for FitAi agents.

All callable tools are decorated with @tool from langchain_core.tools.
Context loaders (for system-prompt injection) are plain functions in CONTEXT_LOADERS.

Startup sequence (called by main.py before any agent invocation):
    from bot.agents.tool_registry import init_tools, init_bot
    init_tools(session)
    init_bot(app)
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from langgraph.types import interrupt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import KNOWLEDGE_BASE_DIR, TELEGRAM_CHAT_ID
from db import queries

LA = ZoneInfo("America/Los_Angeles")

# ---------------------------------------------------------------------------
# Module-level state set at startup
# ---------------------------------------------------------------------------

_session: Session | None = None
_bot_app = None


def init_tools(session: Session) -> None:
    """Set the shared DB session. Must be called at startup before any tool invocation."""
    global _session
    _session = session


def init_bot(app) -> None:
    """Set the Telegram application object. Must be called at startup."""
    global _bot_app
    _bot_app = app


def _get_session() -> Session:
    if _session is None:
        raise RuntimeError("Tool session not initialised — call init_tools(session) at startup")
    return _session


# ---------------------------------------------------------------------------
# Context/data tools
# ---------------------------------------------------------------------------

@tool
def get_health_profile() -> dict | None:
    """Return the most recent lab results as a dict, or None if no profile exists."""
    row = queries.get_latest_health_profile(_get_session())
    if row is None:
        return None
    return {
        "report_date": row.report_date,
        "a1c": row.a1c,
        "a1c_target": row.a1c_target,
        "ldl": row.ldl,
        "ldl_target": row.ldl_target,
        "hdl": row.hdl,
        "triglycerides": row.triglycerides,
        "medications": row.medications,
        "bmi": row.bmi,
        "uploaded_at": row.uploaded_at,
    }


@tool
def get_user_profile() -> dict | None:
    """Return the user profile as a dict, or None if not yet set."""
    row = queries.get_user_profile(_get_session())
    if row is None:
        return None
    return {
        "name": row.name,
        "age": row.age,
        "gender": row.gender,
        "height_cm": row.height_cm,
        "weight_kg": row.weight_kg,
        "diet_type": row.diet_type,
        "allergies": row.allergies,
        "intolerances": row.intolerances,
        "avoided_foods": row.avoided_foods,
        "preferred_cuisines": row.preferred_cuisines,
        "activity_level": row.activity_level,
        "calorie_target": row.calorie_target,
        "protein_target_g": row.protein_target_g,
        "carb_target_g": row.carb_target_g,
        "fat_target_g": row.fat_target_g,
        "fiber_target_g": row.fiber_target_g,
        "step_goal": row.step_goal,
        "sleep_goal_hrs": row.sleep_goal_hrs,
    }


@tool
def get_nutrition_guidance() -> list[dict]:
    """Return all active nutrition guidance rules as a list of dicts."""
    rows = queries.get_active_guidance(_get_session())
    return [
        {
            "id": r.id,
            "rule": r.rule,
            "category": r.category,
            "priority": r.priority,
            "source_lab_date": r.source_lab_date,
        }
        for r in rows
    ]


@tool
def get_semantic_memory() -> list[dict]:
    """Return all semantic memory facts as a list of dicts."""
    return queries.get_semantic_memory(_get_session())


@tool
def query_knowledge_base() -> list[dict]:
    """Load all JSON files from the knowledge base directory and return as a list of dicts."""
    results = []
    for path in Path(KNOWLEDGE_BASE_DIR).glob("*.json"):
        try:
            data = json.loads(path.read_text())
            results.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return results


# ---------------------------------------------------------------------------
# Meal tools
# ---------------------------------------------------------------------------

@tool
def save_meal_analysis(
    meal_type: str,
    foods_identified: list,
    estimated_macros: dict,
    glycemic_load: str,
    cholesterol_flags: list,
    a1c_flags: list,
    score: int,
    telegram_chat_id: int,
) -> str:
    """Save a completed meal analysis to the database. Returns 'saved' on success."""
    now = datetime.now(LA)
    queries.insert_meal_log(
        session=_get_session(),
        date=str(now.date()),
        meal_type=meal_type,
        logged_at=now.isoformat(),
        foods_identified=foods_identified,
        macros=estimated_macros,
        flags={
            "glycemic_load": glycemic_load,
            "cholesterol_flags": cholesterol_flags,
            "a1c_flags": a1c_flags,
        },
        score=score,
    )
    return "saved"


@tool
def query_todays_meals() -> list[dict]:
    """Return all meal logs for today as a list of dicts."""
    rows = queries.get_todays_meals(_get_session())
    return [_meal_row_to_dict(r) for r in rows]


@tool
def query_last_7_days() -> dict:
    """Return meal logs and health logs for the last 7 days as a combined dict."""
    meals = queries.get_meals_last_n_days(_get_session(), 7)
    health = queries.get_last_n_days_health(_get_session(), 7)
    return {
        "meals": [_meal_row_to_dict(r) for r in meals],
        "health": [_health_row_to_dict(r) for r in health],
    }


@tool
def query_week_meals() -> list[dict]:
    """Return all meal logs from the last 7 days as a list of dicts."""
    rows = queries.get_meals_last_n_days(_get_session(), 7)
    return [_meal_row_to_dict(r) for r in rows]


@tool
def query_last_2_days_meals() -> list[dict]:
    """Return all meal logs from the last 2 days as a list of dicts."""
    rows = queries.get_meals_last_n_days(_get_session(), 2)
    return [_meal_row_to_dict(r) for r in rows]


@tool
def query_last_2_days_steps() -> list[dict]:
    """Return step data from daily health logs for the last 2 days."""
    rows = queries.get_last_n_days_health(_get_session(), 2)
    return [
        {
            "date": r.date,
            "steps": r.steps,
            "steps_goal": r.steps_goal,
        }
        for r in rows
    ]


@tool
def query_last_2_days_sleep() -> list[dict]:
    """Return sleep data from daily health logs for the last 2 days."""
    rows = queries.get_last_n_days_health(_get_session(), 2)
    return [
        {
            "date": r.date,
            "sleep_duration_hrs": r.sleep_duration_hrs,
            "sleep_quality": r.sleep_quality,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Health profile tools
# ---------------------------------------------------------------------------

@tool
def save_health_profile(
    report_date: str,
    a1c: float,
    ldl: int,
    hdl: int | None,
    triglycerides: int | None,
    medications: list,
    bmi: float | None,
) -> str:
    """
    Save a lab report as a new health profile row.
    Returns 'saved' on success or 'duplicate_date' if a report for this date already exists.
    """
    try:
        queries.insert_health_profile(
            session=_get_session(),
            report_date=report_date,
            a1c=a1c,
            ldl=ldl,
            hdl=hdl,
            triglycerides=triglycerides,
            medications=medications,
            bmi=bmi,
        )
        return "saved"
    except IntegrityError:
        _get_session().rollback()
        return "duplicate_date"


@tool
def generate_nutrition_guidance(
    new_lab_values: dict,
    deactivate_ids: list[int],
    deactivate_remarks: list[str],
    reactivate_ids: list[int],
    new_rules: list[dict],
) -> str:
    """
    Update nutrition guidance rules based on new lab values.
    Steps: deactivate old rules, reactivate dormant rules, insert new rules.
    Returns 'done'.
    """
    session = _get_session()

    for rule_id, remark in zip(deactivate_ids, deactivate_remarks):
        queries.deactivate_guidance_rule(session, rule_id, remark)

    for rule_id in reactivate_ids:
        queries.reactivate_guidance_rule(session, rule_id)

    for rule in new_rules:
        queries.insert_guidance_rule(
            session=session,
            rule=rule["rule"],
            category=rule["category"],
            source=rule.get("source"),
            priority=rule.get("priority", 1),
            source_lab_date=rule.get("source_lab_date"),
        )

    return "done"


# ---------------------------------------------------------------------------
# Reporting tools
# ---------------------------------------------------------------------------

@tool
def get_last_week_recommendations() -> dict | None:
    """Return the recommendations dict from the most recent weekly report, or None."""
    return queries.get_last_week_recommendations(_get_session())


@tool
def get_sent_callouts(date: str) -> list[str]:
    """Return the list of pattern_type strings already sent on the given date (YYYY-MM-DD)."""
    return queries.get_sent_callouts(_get_session(), date)


# ---------------------------------------------------------------------------
# Knowledge base tool
# ---------------------------------------------------------------------------

@tool
def save_to_knowledge_base(
    filename: str,
    source: str,
    ingested_at: str,
    relevance_tags: list,
    findings: list,
) -> str:
    """Write a research article summary to the knowledge base as a JSON file. Returns 'saved'."""
    data = {
        "source": source,
        "ingested_at": ingested_at,
        "relevance_tags": relevance_tags,
        "findings": findings,
    }
    output_path = Path(KNOWLEDGE_BASE_DIR) / f"{filename}.json"
    output_path.write_text(json.dumps(data, indent=2))
    return "saved"


# ---------------------------------------------------------------------------
# Permission / confirm tools (LangGraph interrupt)
# ---------------------------------------------------------------------------

@tool
def ask_web_search_permission(reason: str) -> str:
    """
    Request permission from the user to search the web for the given reason.
    Pauses the LangGraph run via interrupt() until the user replies.
    Returns the user's answer.
    """
    answer = interrupt(f"I'd like to search the web for {reason}. Can I?")
    return answer


@tool
def confirm_with_user(message: str) -> str:
    """
    Send a confirmation prompt to the user and pause until they reply.
    Returns the user's answer.
    """
    answer = interrupt(message)
    return answer


# ---------------------------------------------------------------------------
# Telegram tool
# ---------------------------------------------------------------------------

@tool
def send_telegram_msg(message: str) -> str:
    """
    Send a Telegram message to the configured chat.
    Returns 'sent' on success.

    Note: asyncio.get_event_loop().run_until_complete() will raise RuntimeError
    if called from within an already-running event loop (e.g. inside an async
    Telegram handler). In that context, use asyncio.ensure_future or schedule
    via the bot's job queue instead. This is a known limitation of this approach.
    """
    if _bot_app is None:
        raise RuntimeError("Bot app not initialised — call init_bot(app) at startup")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        _bot_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    )
    return "sent"


# ---------------------------------------------------------------------------
# Indian food tool
# ---------------------------------------------------------------------------

@tool
def get_indian_food(name: str) -> dict | None:
    """Look up an Indian food item by name. Returns a dict of nutritional values or None."""
    row = queries.get_indian_food_by_name(_get_session(), name)
    if row is None:
        return None
    return {
        "name": row.name,
        "calories_per_100g": row.calories_per_100g,
        "protein_g": row.protein_g,
        "carbs_g": row.carbs_g,
        "fat_g": row.fat_g,
        "fiber_g": row.fiber_g,
        "saturated_fat_g": row.saturated_fat_g,
        "sugar_g": row.sugar_g,
        "glycemic_index": row.glycemic_index,
        "notes": row.notes,
    }


# ---------------------------------------------------------------------------
# Internal ORM → dict helpers
# ---------------------------------------------------------------------------

def _meal_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "date": row.date,
        "meal_type": row.meal_type,
        "logged_at": row.logged_at,
        "foods_identified": row.foods_identified,
        "macros": row.macros,
        "flags": row.flags,
        "score": row.score,
    }


def _health_row_to_dict(row) -> dict:
    return {
        "date": row.date,
        "steps": row.steps,
        "steps_goal": row.steps_goal,
        "sleep_duration_hrs": row.sleep_duration_hrs,
        "sleep_quality": row.sleep_quality,
        "fetched_at": row.fetched_at,
    }


# ---------------------------------------------------------------------------
# TOOL_REGISTRY
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, object] = {
    "get_health_profile": get_health_profile,
    "get_user_profile": get_user_profile,
    "get_nutrition_guidance": get_nutrition_guidance,
    "get_semantic_memory": get_semantic_memory,
    "query_knowledge_base": query_knowledge_base,
    "save_meal_analysis": save_meal_analysis,
    "query_todays_meals": query_todays_meals,
    "query_last_7_days": query_last_7_days,
    "query_week_meals": query_week_meals,
    "query_last_2_days_meals": query_last_2_days_meals,
    "query_last_2_days_steps": query_last_2_days_steps,
    "query_last_2_days_sleep": query_last_2_days_sleep,
    "save_health_profile": save_health_profile,
    "generate_nutrition_guidance": generate_nutrition_guidance,
    "get_last_week_recommendations": get_last_week_recommendations,
    "get_sent_callouts": get_sent_callouts,
    "save_to_knowledge_base": save_to_knowledge_base,
    "ask_web_search_permission": ask_web_search_permission,
    "confirm_with_user": confirm_with_user,
    "send_telegram_msg": send_telegram_msg,
    "get_indian_food": get_indian_food,
}

# ---------------------------------------------------------------------------
# CONTEXT_LOADERS — return formatted string blocks for system-prompt injection
# ---------------------------------------------------------------------------

def _load_health_profile_context() -> str:
    """Return a formatted === LATEST LAB RESULTS === block for system prompt injection."""
    row = queries.get_latest_health_profile(_get_session())
    if row is None:
        return "=== LATEST LAB RESULTS ===\nNo lab results on file yet.\n"
    meds = ", ".join(row.medications) if row.medications else "none"
    return (
        f"=== LATEST LAB RESULTS ({row.report_date}) ===\n"
        f"A1C: {row.a1c}%  (target: <5.7%)\n"
        f"LDL: {row.ldl} mg/dL  (target: <100)\n"
        f"HDL: {row.hdl} mg/dL  (target: >60)\n"
        f"Triglycerides: {row.triglycerides} mg/dL\n"
        f"Medications: {meds}\n"
        f"BMI: {row.bmi}\n"
    )


def _load_user_profile_context() -> str:
    """Return a formatted === USER PROFILE === block for system prompt injection."""
    row = queries.get_user_profile(_get_session())
    if row is None:
        return "=== USER PROFILE ===\nNo user profile set yet.\n"
    return (
        f"=== USER PROFILE ===\n"
        f"Name: {row.name}, Age: {row.age}, Gender: {row.gender}\n"
        f"Height: {row.height_cm}cm, Weight: {row.weight_kg}kg\n"
        f"Diet: {row.diet_type}\n"
        f"Allergies: {row.allergies or 'none'}  |  Intolerances: {row.intolerances or 'none'}\n"
        f"Avoided foods: {row.avoided_foods or 'none'}\n"
        f"Preferred cuisines: {row.preferred_cuisines or 'none'}\n"
        f"Activity level: {row.activity_level}\n"
        f"Goals: {row.step_goal} steps/day, {row.sleep_goal_hrs}hrs sleep\n"
        f"\nMacro targets: {row.calorie_target} kcal · "
        f"{row.protein_target_g}g protein · {row.carb_target_g}g carbs · "
        f"{row.fat_target_g}g fat · {row.fiber_target_g}g fiber\n"
    )


def _load_nutrition_guidance_context() -> str:
    """Return a formatted === PERSONALISED NUTRITION RULES === block."""
    rows = queries.get_active_guidance(_get_session())
    if not rows:
        return "=== PERSONALISED NUTRITION RULES ===\nNo nutrition rules set yet.\n"
    lines = ["=== PERSONALISED NUTRITION RULES ==="]
    for r in rows:
        lines.append(f"[{r.category}] {r.rule}")
    return "\n".join(lines) + "\n"


def _load_semantic_memory_context() -> str:
    """Return a formatted === SEMANTIC MEMORY === block."""
    facts = queries.get_semantic_memory(_get_session())
    if not facts:
        return "=== SEMANTIC MEMORY ===\nNo semantic memory yet.\n"
    updated = facts[0].get("valid_from", "") if facts else ""
    lines = [f"=== SEMANTIC MEMORY (as of {updated}) ==="]
    for f in facts:
        lines.append(f"• {f['fact']}")
    return "\n".join(lines) + "\n"


def _load_knowledge_base_context() -> str:
    """Return a formatted === KNOWLEDGE BASE === block from all JSON files."""
    articles = []
    for path in Path(KNOWLEDGE_BASE_DIR).glob("*.json"):
        try:
            data = json.loads(path.read_text())
            articles.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    if not articles:
        return "=== KNOWLEDGE BASE ===\nNo research articles ingested yet.\n"
    lines = ["=== KNOWLEDGE BASE ==="]
    for article in articles:
        lines.append(f"\nSource: {article.get('source', 'unknown')}")
        for finding in article.get("findings", []):
            lines.append(f"  • {finding}")
    return "\n".join(lines) + "\n"


CONTEXT_LOADERS: dict[str, callable] = {
    "health_profile": _load_health_profile_context,
    "user_profile": _load_user_profile_context,
    "nutrition_guidance": _load_nutrition_guidance_context,
    "semantic_memory": _load_semantic_memory_context,
    "knowledge_base": _load_knowledge_base_context,
}

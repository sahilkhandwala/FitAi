"""
All database query functions for FitAi.

Rules:
- Every function takes a SQLAlchemy Session as its first arg
- No raw SQL — use ORM only
- No user_id parameter — single-user app
- All times in America/Los_Angeles via zoneinfo
- JSON columns encode/decode at the model layer (JSONType TypeDecorator) — no json.dumps here
- IntegrityError from insert_health_profile bubbles up naturally — do NOT catch it
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, delete, desc, func
from sqlalchemy.orm import Session

from db.models import (
    DailyHealthLog,
    DailySummary,
    IndianFood,
    MealLog,
    Pattern,
    UserHealthProfile,
    UserNutritionGuidance,
    UserProfile,
    UserSemanticMemory,
    WeeklyReport,
)

LA = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# meal_logs
# ---------------------------------------------------------------------------

def insert_meal_log(
    session: Session,
    date: str,
    meal_type: str,
    logged_at: str,
    foods_identified: list,
    macros: dict,
    flags: dict,
    score: int | None,
) -> int:
    """Insert a meal log row. Returns the new row id."""
    row = MealLog(
        date=date,
        meal_type=meal_type,
        logged_at=logged_at,
        foods_identified=foods_identified,
        macros=macros,
        flags=flags,
        score=score,
    )
    session.add(row)
    session.flush()  # populate row.id without committing
    session.commit()
    return row.id


def get_meals_by_date(session: Session, date: str) -> list[MealLog]:
    """Return all meal log rows for a given ISO date. Empty list if none."""
    result = session.execute(
        select(MealLog).where(MealLog.date == date).order_by(MealLog.logged_at)
    )
    return list(result.scalars().all())


def get_todays_meals(session: Session) -> list[MealLog]:
    """Return all meal log rows for today (America/Los_Angeles)."""
    today = str(datetime.now(LA).date())
    return get_meals_by_date(session, today)


def get_meals_last_n_days(session: Session, n: int) -> list[MealLog]:
    """Return meal log rows from the last n days (today inclusive)."""
    today = datetime.now(LA).date()
    cutoff = str(today - timedelta(days=n - 1))
    result = session.execute(
        select(MealLog)
        .where(MealLog.date >= cutoff)
        .order_by(MealLog.date, MealLog.logged_at)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# daily_health_logs
# ---------------------------------------------------------------------------

def upsert_daily_health_log(
    session: Session,
    date: str,
    steps: int | None,
    steps_goal: int,
    sleep_duration_hrs: float | None,
    sleep_quality: str | None,
) -> None:
    """Insert or update a daily health log row (keyed on date)."""
    row = session.get(DailyHealthLog, date)
    if row is None:
        row = DailyHealthLog(date=date)
        session.add(row)
    row.steps = steps
    row.steps_goal = steps_goal
    row.sleep_duration_hrs = sleep_duration_hrs
    row.sleep_quality = sleep_quality
    row.fetched_at = datetime.now(LA).isoformat()
    session.commit()


def get_health_log_by_date(session: Session, date: str) -> DailyHealthLog | None:
    """Return the daily health log row for a given date, or None."""
    return session.get(DailyHealthLog, date)


def get_last_n_days_health(session: Session, n: int) -> list[DailyHealthLog]:
    """Return daily health log rows from the last n days."""
    today = datetime.now(LA).date()
    cutoff = str(today - timedelta(days=n - 1))
    result = session.execute(
        select(DailyHealthLog)
        .where(DailyHealthLog.date >= cutoff)
        .order_by(DailyHealthLog.date)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# user_profile
# ---------------------------------------------------------------------------

def upsert_user_profile(session: Session, **kwargs) -> None:
    """
    Insert or update the single user profile row (id=1).
    Only the provided keyword fields are updated — other fields are preserved.
    """
    row = session.get(UserProfile, 1)
    if row is None:
        row = UserProfile(id=1)
        session.add(row)
    for key, value in kwargs.items():
        if hasattr(row, key):
            setattr(row, key, value)
    row.updated_at = datetime.now(LA).isoformat()
    session.commit()


def get_user_profile(session: Session) -> UserProfile | None:
    """Return the single user profile row, or None if not yet set."""
    return session.get(UserProfile, 1)


# ---------------------------------------------------------------------------
# user_health_profile
# ---------------------------------------------------------------------------

def insert_health_profile(
    session: Session,
    report_date: str,
    a1c: float | None,
    ldl: int | None,
    hdl: int | None,
    triglycerides: int | None,
    medications: list,
    bmi: float | None,
    a1c_target: float | None = None,
    ldl_target: int | None = None,
) -> None:
    """
    Insert a new health profile row.
    Raises sqlalchemy.exc.IntegrityError on duplicate report_date — caller handles it.
    """
    row = UserHealthProfile(
        report_date=report_date,
        a1c=a1c,
        a1c_target=a1c_target,
        ldl=ldl,
        ldl_target=ldl_target,
        hdl=hdl,
        triglycerides=triglycerides,
        medications=medications,
        bmi=bmi,
    )
    session.add(row)
    session.commit()  # IntegrityError bubbles up here if report_date is duplicate


def get_latest_health_profile(session: Session) -> UserHealthProfile | None:
    """Return the most recent health profile row by report_date, or None."""
    return session.execute(
        select(UserHealthProfile)
        .order_by(desc(UserHealthProfile.report_date))
        .limit(1)
    ).scalar_one_or_none()


def get_health_profile_trend(session: Session) -> list[tuple]:
    """
    Return (report_date, a1c, ldl, hdl) tuples ordered by report_date ascending.
    Used by WeeklyReportAgent and HealthInsightsAgent for trend analysis.
    """
    result = session.execute(
        select(
            UserHealthProfile.report_date,
            UserHealthProfile.a1c,
            UserHealthProfile.ldl,
            UserHealthProfile.hdl,
        ).order_by(UserHealthProfile.report_date)
    )
    return list(result.all())


# ---------------------------------------------------------------------------
# user_nutrition_guidance
# ---------------------------------------------------------------------------

def insert_guidance_rule(
    session: Session,
    rule: str,
    category: str,
    source: str | None,
    priority: int,
    source_lab_date: str | None,
) -> int:
    """Insert a new nutrition guidance rule. Returns the new row id."""
    row = UserNutritionGuidance(
        rule=rule,
        category=category,
        source=source,
        priority=priority,
        source_lab_date=source_lab_date,
        is_active=1,
    )
    session.add(row)
    session.flush()
    session.commit()
    return row.id


def get_active_guidance(session: Session) -> list[UserNutritionGuidance]:
    """Return all active nutrition guidance rules (is_active=1)."""
    result = session.execute(
        select(UserNutritionGuidance)
        .where(UserNutritionGuidance.is_active == 1)
        .order_by(UserNutritionGuidance.priority.desc(), UserNutritionGuidance.created_at)
    )
    return list(result.scalars().all())


def deactivate_guidance_rule(session: Session, rule_id: int, remark: str) -> None:
    """Set a guidance rule to inactive with a remark explaining why."""
    row = session.get(UserNutritionGuidance, rule_id)
    if row is None:
        raise ValueError(f"Guidance rule {rule_id} not found")
    row.is_active = 0
    row.remark = remark
    row.deactivated_at = datetime.now(LA).isoformat()
    session.commit()


def reactivate_guidance_rule(session: Session, rule_id: int) -> None:
    """Reactivate a previously deactivated guidance rule, clearing remark and deactivated_at."""
    row = session.get(UserNutritionGuidance, rule_id)
    if row is None:
        raise ValueError(f"Guidance rule {rule_id} not found")
    row.is_active = 1
    row.remark = None
    row.deactivated_at = None
    session.commit()


# ---------------------------------------------------------------------------
# user_semantic_memory
# ---------------------------------------------------------------------------

def replace_semantic_memory(session: Session, facts: list[dict]) -> None:
    """
    Full replacement — delete all existing rows, then bulk insert new ones.
    Runs in a single transaction.
    """
    session.execute(delete(UserSemanticMemory))
    for fact in facts:
        row = UserSemanticMemory(
            category=fact["category"],
            fact=fact["fact"],
            confidence=fact["confidence"],
            evidence=fact.get("evidence"),
            valid_from=fact["valid_from"],
        )
        session.add(row)
    session.commit()


def get_semantic_memory(session: Session) -> list[dict]:
    """Return all semantic memory facts as a list of dicts."""
    result = session.execute(
        select(UserSemanticMemory).order_by(UserSemanticMemory.id)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "fact": r.fact,
            "confidence": r.confidence,
            "evidence": r.evidence,
            "valid_from": r.valid_from,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# daily_summaries
# ---------------------------------------------------------------------------

def upsert_daily_summary(
    session: Session,
    date: str,
    total_macros: dict,
    dietary_score: int,
    improvements: list,
) -> None:
    """Insert or update a daily summary (keyed on date)."""
    row = session.get(DailySummary, date)
    if row is None:
        row = DailySummary(date=date)
        session.add(row)
    row.total_macros = total_macros
    row.dietary_score = dietary_score
    row.improvements = improvements
    session.commit()


def get_daily_summary(session: Session, date: str) -> DailySummary | None:
    """Return the daily summary for a given date, or None."""
    return session.get(DailySummary, date)


# ---------------------------------------------------------------------------
# weekly_reports
# ---------------------------------------------------------------------------

def upsert_weekly_report(
    session: Session,
    week_start: str,
    avg_dietary_score: int,
    score_delta: int,
    patterns_detected: list,
    recommendations: dict,
) -> None:
    """Insert or update a weekly report (keyed on week_start)."""
    row = session.get(WeeklyReport, week_start)
    if row is None:
        row = WeeklyReport(week_start=week_start)
        session.add(row)
    row.avg_dietary_score = avg_dietary_score
    row.score_delta = score_delta
    row.patterns_detected = patterns_detected
    row.recommendations = recommendations
    session.commit()


def get_weekly_report(session: Session, week_start: str) -> WeeklyReport | None:
    """Return the weekly report for a given week_start date, or None."""
    return session.get(WeeklyReport, week_start)


def get_last_week_recommendations(session: Session) -> dict | None:
    """Return the recommendations dict from the most recent weekly report, or None."""
    row = session.execute(
        select(WeeklyReport).order_by(desc(WeeklyReport.week_start)).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return row.recommendations


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------

def insert_pattern(
    session: Session,
    date: str,
    pattern_type: str,
    streak_days: int,
) -> int:
    """Insert a pattern callout row. Returns the new row id."""
    row = Pattern(
        date=date,
        pattern_type=pattern_type,
        streak_days=streak_days,
        sent_at=datetime.now(LA).isoformat(),
    )
    session.add(row)
    session.flush()
    session.commit()
    return row.id


def get_patterns_last_7_days(session: Session) -> list[Pattern]:
    """Return all pattern rows from the last 7 days."""
    today = datetime.now(LA).date()
    cutoff = str(today - timedelta(days=6))
    result = session.execute(
        select(Pattern)
        .where(Pattern.date >= cutoff)
        .order_by(Pattern.date)
    )
    return list(result.scalars().all())


def get_sent_callouts(session: Session, date: str) -> list[str]:
    """Return list of pattern_type strings that were already sent on a given date."""
    result = session.execute(
        select(Pattern.pattern_type).where(Pattern.date == date)
    )
    return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# indian_foods
# ---------------------------------------------------------------------------

def upsert_indian_food(
    session: Session,
    name: str,
    calories_per_100g: float | None,
    protein_g: float | None,
    carbs_g: float | None,
    fat_g: float | None,
    fiber_g: float | None,
    saturated_fat_g: float | None,
    sugar_g: float | None,
    glycemic_index: int | None,
    notes: str | None,
) -> None:
    """Insert or update an Indian food entry (keyed on name)."""
    row = session.execute(
        select(IndianFood).where(IndianFood.name == name)
    ).scalar_one_or_none()
    if row is None:
        row = IndianFood(name=name)
        session.add(row)
    row.calories_per_100g = calories_per_100g
    row.protein_g = protein_g
    row.carbs_g = carbs_g
    row.fat_g = fat_g
    row.fiber_g = fiber_g
    row.saturated_fat_g = saturated_fat_g
    row.sugar_g = sugar_g
    row.glycemic_index = glycemic_index
    row.notes = notes
    session.commit()


def get_indian_food_by_name(session: Session, name: str) -> IndianFood | None:
    """Return an Indian food row by name, or None if not found."""
    return session.execute(
        select(IndianFood).where(IndianFood.name == name)
    ).scalar_one_or_none()

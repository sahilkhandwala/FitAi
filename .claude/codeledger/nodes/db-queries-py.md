# db/queries.py

## Summary
All database query functions for FitAi. Every function takes a SQLAlchemy Session as its first argument. Uses ORM only — no raw SQL. Single-user app so no user_id scoping. JSON columns are handled by the JSONType decorator in models.py. IntegrityError from insert_health_profile bubbles up to callers.

## Functions
- insert_meal_log(session, date, meal_type, logged_at, foods_identified, macros, flags, score) → int — inserts meal log row, returns new id
- get_meals_by_date(session, date) → list[MealLog] — returns meals for a specific ISO date
- get_todays_meals(session) → list[MealLog] — returns today's meals in LA timezone
- get_meals_last_n_days(session, n) → list[MealLog] — returns meals from last n days inclusive
- upsert_daily_health_log(session, date, steps, steps_goal, sleep_duration_hrs, sleep_quality) → None — insert or update health log
- get_health_log_by_date(session, date) → DailyHealthLog | None
- get_last_n_days_health(session, n) → list[DailyHealthLog] — returns health logs from last n days
- upsert_user_profile(session, **kwargs) → None — insert or update singleton user profile (id=1)
- get_user_profile(session) → UserProfile | None
- insert_health_profile(session, report_date, a1c, ldl, hdl, triglycerides, medications, bmi, a1c_target, ldl_target) → None — raises IntegrityError on duplicate report_date
- get_latest_health_profile(session) → UserHealthProfile | None — most recent by report_date
- get_health_profile_trend(session) → list[tuple] — (report_date, a1c, ldl, hdl) ordered ascending
- insert_guidance_rule(session, rule, category, source, priority, source_lab_date) → int — returns new id
- get_active_guidance(session) → list[UserNutritionGuidance] — only is_active=1 rows
- deactivate_guidance_rule(session, rule_id, remark) → None — sets is_active=0
- reactivate_guidance_rule(session, rule_id) → None — sets is_active=1, clears remark
- replace_semantic_memory(session, facts) → None — deletes all rows, bulk inserts new ones
- get_semantic_memory(session) → list[dict] — all facts as dicts with id/category/fact/confidence/evidence/valid_from/updated_at
- upsert_daily_summary(session, date, total_macros, dietary_score, improvements) → None
- get_daily_summary(session, date) → DailySummary | None
- upsert_weekly_report(session, week_start, avg_dietary_score, score_delta, patterns_detected, recommendations) → None
- get_weekly_report(session, week_start) → WeeklyReport | None
- get_last_week_recommendations(session) → dict | None — recommendations from most recent weekly report
- insert_pattern(session, date, pattern_type, streak_days) → int — returns new id
- get_patterns_last_7_days(session) → list[Pattern]
- get_sent_callouts(session, date) → list[str] — pattern_type strings sent on given date
- upsert_indian_food(session, name, calories_per_100g, protein_g, carbs_g, fat_g, fiber_g, saturated_fat_g, sugar_g, glycemic_index, notes) → None
- get_indian_food_by_name(session, name) → IndianFood | None

## Non-function code
- `LA` — ZoneInfo("America/Los_Angeles") module-level constant

## Imports
- datetime, timedelta, ZoneInfo
- sqlalchemy (select, delete, desc, func), sqlalchemy.orm.Session
- db.models (all model classes)

## Imported by
- bot/agents/tool_registry.py — all tools call queries functions via _get_session()
- tests/unit/test_db_queries.py — direct query function tests
- tests/unit/test_tool_registry.py — uses get_todays_meals for verification

## Tags
db, queries, orm, sqlite, data-access

## Node path
db/queries.py

# db/models.py

## Summary
SQLAlchemy 2.0 ORM models for all 10 FitAi database tables. Defines a custom JSONType TypeDecorator that transparently encodes/decodes Python dicts and lists to/from SQLite TEXT columns, so callers never need json.dumps/loads. All models inherit from DeclarativeBase.

## Functions
- JSONType.process_bind_param(value, dialect) — encodes Python value to JSON string for DB storage
- JSONType.process_result_value(value, dialect) — decodes JSON string from DB to Python value

## Non-function code
- `JSONType` — TypeDecorator (impl=TEXT) for automatic JSON serialisation in all JSON columns
- `Base` — DeclarativeBase for all models
- `_NOW` — SQLite server-default expression `datetime('now')`
- `DailyHealthLog` — table daily_health_logs: date (PK), steps, steps_goal, sleep_duration_hrs, sleep_quality, fetched_at
- `MealLog` — table meal_logs: id (PK, AI), date, meal_type, logged_at, foods_identified (JSON), macros (JSON), flags (JSON), score
- `UserProfile` — table user_profile: id=1 (singleton enforced by CHECK constraint), demographics, diet, targets, goals
- `UserHealthProfile` — table user_health_profile: id (PK, AI), report_date (UNIQUE), a1c, ldl, hdl, triglycerides, medications (JSON), bmi
- `UserNutritionGuidance` — table user_nutrition_guidance: id (PK, AI), rule, category, is_active, priority, remark, source_lab_date
- `DailySummary` — table daily_summaries: date (PK), total_macros (JSON), dietary_score, improvements (JSON), sent_at
- `WeeklyReport` — table weekly_reports: week_start (PK), avg_dietary_score, score_delta, patterns_detected (JSON), recommendations (JSON), skip_comparison, sent_at
- `Pattern` — table patterns: id (PK, AI), date, pattern_type, streak_days, sent_at
- `UserSemanticMemory` — table user_semantic_memory: id (PK, AI), category, fact, confidence, evidence, valid_from, updated_at
- `IndianFood` — table indian_foods: id (PK, AI), name (UNIQUE), per-100g macros, glycemic_index, notes

## Imports
- json, sqlalchemy (Column, Float, Integer, Text, text, CheckConstraint), sqlalchemy.orm.DeclarativeBase, sqlalchemy.types (TypeDecorator, TEXT)

## Imported by
- db/queries.py — imports all model classes for ORM queries
- tests/conftest.py — imports Base for create_all in in-memory test DB
- tests/unit/test_tool_registry.py — imports UserHealthProfile, UserNutritionGuidance for direct row insertion in tests

## Tags
db, models, orm, sqlite, schema

## Node path
db/models.py

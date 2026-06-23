# models.py

## Summary
SQLAlchemy 2.0 ORM models for all 10 FitAi database tables. Uses `DeclarativeBase` pattern. Defines a `JSONType` TypeDecorator that transparently encodes Python dicts/lists to JSON strings on write and decodes on read, so queries.py never needs to call json.dumps/loads. All float columns use `Float` (maps to SQLite REAL). Timestamp `server_default` columns use `text("(datetime('now'))")` for proper SQLite DDL parenthesization.

## Functions
- JSONType.process_bind_param(value, dialect) — encodes Python value to JSON string for storage
- JSONType.process_result_value(value, dialect) — decodes JSON string back to Python on retrieval

## Non-function code
- `_NOW = text("(datetime('now'))")` — reusable server_default for timestamp columns
- `Base` — DeclarativeBase subclass, all models inherit from it
- `DailyHealthLog` — daily_health_logs table (Fitbit steps + sleep)
- `MealLog` — meal_logs table (per-meal food analysis)
- `UserProfile` — user_profile table (single row, id=1 enforced by CheckConstraint)
- `UserHealthProfile` — user_health_profile table (lab reports, one per report_date UNIQUE)
- `UserNutritionGuidance` — user_nutrition_guidance table (append-with-status rules)
- `DailySummary` — daily_summaries table (daily dietary summary)
- `WeeklyReport` — weekly_reports table (weekly analysis)
- `Pattern` — patterns table (streak tracking for callouts)
- `UserSemanticMemory` — user_semantic_memory table (weekly-refreshed behavioral facts)
- `IndianFood` — indian_foods table (IFCT/NIN macro lookup)

## Imports
- sqlalchemy — CheckConstraint, Column, Float, Integer, Text, text
- sqlalchemy.orm — DeclarativeBase
- sqlalchemy.types — TypeDecorator, TEXT
- json — used inside JSONType TypeDecorator

## Imported by
- db/__init__.py — imports Base for create_all
- db/queries.py — imports all 10 model classes
- tests/conftest.py — imports Base for test engine setup

## Tags
database, models, orm, sqlalchemy, sqlite

## Node path
db/models.py

"""
SQLAlchemy 2.0 ORM models for FitAi — all 10 tables.

JSON columns use a TypeDecorator so encode/decode is handled at the column level.
This means:
  - You pass plain Python dicts/lists into queries.py
  - You get back plain Python dicts/lists from ORM attributes
  - No json.dumps/loads needed in queries.py
"""

import json
from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator, TEXT

_NOW = text("(datetime('now'))")


class JSONType(TypeDecorator):
    """Stores Python dicts/lists as JSON strings in SQLite TEXT columns."""

    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


class Base(DeclarativeBase):
    pass


class DailyHealthLog(Base):
    __tablename__ = "daily_health_logs"

    date = Column(Text, primary_key=True)
    steps = Column(Integer)
    steps_goal = Column(Integer, nullable=False, default=10000)
    sleep_duration_hrs = Column(Float)
    sleep_quality = Column(Text)
    fetched_at = Column(Text, nullable=False, server_default=_NOW)


class MealLog(Base):
    __tablename__ = "meal_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False)
    meal_type = Column(Text, nullable=False)
    logged_at = Column(Text, nullable=False)
    foods_identified = Column(JSONType)
    macros = Column(JSONType)
    flags = Column(JSONType)
    score = Column(Integer)


class UserProfile(Base):
    __tablename__ = "user_profile"

    id = Column(Integer, primary_key=True, default=1)
    name = Column(Text)
    age = Column(Integer)
    gender = Column(Text)
    height_cm = Column(Float)
    weight_kg = Column(Float)
    diet_type = Column(Text)
    allergies = Column(JSONType)
    intolerances = Column(JSONType)
    avoided_foods = Column(JSONType)
    preferred_cuisines = Column(JSONType)
    activity_level = Column(Text)
    calorie_target = Column(Integer)
    protein_target_g = Column(Integer)
    carb_target_g = Column(Integer)
    fat_target_g = Column(Integer)
    fiber_target_g = Column(Integer)
    step_goal = Column(Integer, default=10000)
    sleep_goal_hrs = Column(Float, default=7.0)
    updated_at = Column(Text, nullable=False, server_default=_NOW)

    __table_args__ = (CheckConstraint("id = 1", name="ck_user_profile_single_row"),)


class UserHealthProfile(Base):
    __tablename__ = "user_health_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Text, nullable=False, unique=True)
    a1c = Column(Float)
    a1c_target = Column(Float)
    ldl = Column(Integer)
    ldl_target = Column(Integer)
    hdl = Column(Integer)
    triglycerides = Column(Integer)
    medications = Column(JSONType)
    bmi = Column(Float)
    uploaded_at = Column(Text, nullable=False, server_default=_NOW)


class UserNutritionGuidance(Base):
    __tablename__ = "user_nutrition_guidance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    source = Column(Text)
    priority = Column(Integer, default=1)
    is_active = Column(Integer, nullable=False, default=1)
    remark = Column(Text)
    source_lab_date = Column(Text)
    created_at = Column(Text, nullable=False, server_default=_NOW)
    deactivated_at = Column(Text)


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    date = Column(Text, primary_key=True)
    total_macros = Column(JSONType)
    dietary_score = Column(Integer)
    improvements = Column(JSONType)
    sent_at = Column(Text)


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    week_start = Column(Text, primary_key=True)
    avg_dietary_score = Column(Integer)
    score_delta = Column(Integer)
    patterns_detected = Column(JSONType)
    recommendations = Column(JSONType)
    skip_comparison = Column(Integer, default=0)
    sent_at = Column(Text)


class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False)
    pattern_type = Column(Text, nullable=False)
    streak_days = Column(Integer, nullable=False)
    sent_at = Column(Text)


class UserSemanticMemory(Base):
    __tablename__ = "user_semantic_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(Text, nullable=False)
    fact = Column(Text, nullable=False)
    confidence = Column(Text, nullable=False)
    evidence = Column(Text)
    valid_from = Column(Text, nullable=False)
    updated_at = Column(Text, nullable=False, server_default=_NOW)


class IndianFood(Base):
    __tablename__ = "indian_foods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    calories_per_100g = Column(Float)
    protein_g = Column(Float)
    carbs_g = Column(Float)
    fat_g = Column(Float)
    fiber_g = Column(Float)
    saturated_fat_g = Column(Float)
    sugar_g = Column(Float)
    glycemic_index = Column(Integer)
    notes = Column(Text)

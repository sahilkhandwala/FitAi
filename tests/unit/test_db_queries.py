"""
Unit tests for db/queries.py — written BEFORE implementation (TDD).

All tests use an in-memory SQLite DB via the `session` fixture from conftest.py.
These tests will fail with ImportError until db/queries.py and db/models.py exist.
"""

import json
import pytest
from datetime import date
from zoneinfo import ZoneInfo

import sqlalchemy.exc

from db import queries


# ---------------------------------------------------------------------------
# meal_logs
# ---------------------------------------------------------------------------

class TestMealLogs:
    def test_insert_meal_log_returns_id(self, session):
        row_id = queries.insert_meal_log(
            session,
            date="2026-06-20",
            meal_type="breakfast",
            logged_at="2026-06-20T08:00:00",
            foods_identified=["oats", "banana"],
            macros={"calories": 350, "protein": 12, "carbs": 60, "fat": 5},
            flags={"high_gi": False},
            score=85,
        )
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_get_meals_by_date_returns_rows(self, session):
        queries.insert_meal_log(
            session,
            date="2026-06-20",
            meal_type="lunch",
            logged_at="2026-06-20T13:00:00",
            foods_identified=["rice", "dal"],
            macros={"calories": 500},
            flags={},
            score=70,
        )
        rows = queries.get_meals_by_date(session, "2026-06-20")
        assert len(rows) == 1
        assert rows[0].meal_type == "lunch"

    def test_get_meals_by_date_empty_list_when_no_rows(self, session):
        rows = queries.get_meals_by_date(session, "2099-01-01")
        assert rows == []

    def test_get_meals_by_date_multiple_same_day(self, session):
        for meal_type in ("breakfast", "lunch", "dinner"):
            queries.insert_meal_log(
                session,
                date="2026-06-21",
                meal_type=meal_type,
                logged_at=f"2026-06-21T{'08' if meal_type == 'breakfast' else '13' if meal_type == 'lunch' else '19'}:00:00",
                foods_identified=["food"],
                macros={"calories": 400},
                flags={},
                score=80,
            )
        rows = queries.get_meals_by_date(session, "2026-06-21")
        assert len(rows) == 3

    def test_get_todays_meals_uses_la_date(self, session):
        today_la = str(date.today())
        queries.insert_meal_log(
            session,
            date=today_la,
            meal_type="snack",
            logged_at=f"{today_la}T15:00:00",
            foods_identified=["apple"],
            macros={"calories": 80},
            flags={},
            score=90,
        )
        rows = queries.get_todays_meals(session)
        assert len(rows) >= 1
        assert any(r.meal_type == "snack" for r in rows)

    def test_get_meals_last_n_days_n2(self, session):
        for d in ("2026-06-19", "2026-06-20", "2026-06-21"):
            queries.insert_meal_log(
                session,
                date=d,
                meal_type="breakfast",
                logged_at=f"{d}T08:00:00",
                foods_identified=["egg"],
                macros={"calories": 200},
                flags={},
                score=88,
            )
        rows = queries.get_meals_last_n_days(session, 2)
        dates = {r.date for r in rows}
        assert "2026-06-19" not in dates
        assert len(dates) <= 2

    def test_get_meals_last_n_days_n7(self, session):
        rows = queries.get_meals_last_n_days(session, 7)
        assert isinstance(rows, list)

    def test_meal_log_foods_identified_is_parsed(self, session):
        """foods_identified stored as JSON, returned as list."""
        queries.insert_meal_log(
            session,
            date="2026-06-20",
            meal_type="dinner",
            logged_at="2026-06-20T19:00:00",
            foods_identified=["chapati", "sabzi"],
            macros={"calories": 450},
            flags={"a1c_flag": True},
            score=75,
        )
        rows = queries.get_meals_by_date(session, "2026-06-20")
        assert isinstance(rows[0].foods_identified, list)
        assert "chapati" in rows[0].foods_identified

    def test_meal_log_macros_is_parsed(self, session):
        """macros stored as JSON, returned as dict."""
        queries.insert_meal_log(
            session,
            date="2026-06-20",
            meal_type="breakfast",
            logged_at="2026-06-20T08:30:00",
            foods_identified=["poha"],
            macros={"calories": 300, "protein": 8},
            flags={},
            score=82,
        )
        rows = queries.get_meals_by_date(session, "2026-06-20")
        assert isinstance(rows[0].macros, dict)
        assert rows[0].macros["calories"] == 300


# ---------------------------------------------------------------------------
# daily_health_logs
# ---------------------------------------------------------------------------

class TestDailyHealthLogs:
    def test_upsert_creates_row(self, session):
        queries.upsert_daily_health_log(
            session,
            date="2026-06-20",
            steps=8500,
            steps_goal=10000,
            sleep_duration_hrs=7.2,
            sleep_quality="good",
        )
        row = queries.get_health_log_by_date(session, "2026-06-20")
        assert row is not None
        assert row.steps == 8500

    def test_upsert_updates_existing_row(self, session):
        queries.upsert_daily_health_log(
            session,
            date="2026-06-20",
            steps=5000,
            steps_goal=10000,
            sleep_duration_hrs=6.0,
            sleep_quality="fair",
        )
        queries.upsert_daily_health_log(
            session,
            date="2026-06-20",
            steps=9000,
            steps_goal=10000,
            sleep_duration_hrs=7.5,
            sleep_quality="good",
        )
        row = queries.get_health_log_by_date(session, "2026-06-20")
        assert row.steps == 9000
        assert row.sleep_quality == "good"

    def test_get_health_log_by_date_none_when_missing(self, session):
        row = queries.get_health_log_by_date(session, "2099-01-01")
        assert row is None

    def test_get_last_n_days_health(self, session):
        from datetime import datetime, timedelta
        today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
        for delta in (2, 1, 0):
            d = str(today - timedelta(days=delta))
            queries.upsert_daily_health_log(
                session,
                date=d,
                steps=7000,
                steps_goal=10000,
                sleep_duration_hrs=7.0,
                sleep_quality="good",
            )
        rows = queries.get_last_n_days_health(session, 7)
        assert isinstance(rows, list)
        assert len(rows) >= 3

    def test_get_last_n_days_health_gap_handling(self, session):
        """Missing days should not crash — just return what exists."""
        queries.upsert_daily_health_log(
            session,
            date="2026-06-15",
            steps=6000,
            steps_goal=10000,
            sleep_duration_hrs=6.5,
            sleep_quality="fair",
        )
        rows = queries.get_last_n_days_health(session, 7)
        assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# user_profile
# ---------------------------------------------------------------------------

class TestUserProfile:
    def test_get_user_profile_none_when_empty(self, session):
        result = queries.get_user_profile(session)
        assert result is None

    def test_upsert_creates_profile(self, session):
        queries.upsert_user_profile(
            session,
            name="Sahil",
            age=30,
            gender="male",
            height_cm=178.0,
            weight_kg=75.0,
            diet_type="omnivore",
            calorie_target=2000,
        )
        profile = queries.get_user_profile(session)
        assert profile is not None
        assert profile.name == "Sahil"
        assert profile.age == 30

    def test_upsert_updates_existing_profile(self, session):
        queries.upsert_user_profile(session, name="Sahil", age=30)
        queries.upsert_user_profile(session, name="Sahil", age=31, weight_kg=74.5)
        profile = queries.get_user_profile(session)
        assert profile.age == 31
        assert profile.weight_kg == 74.5

    def test_profile_always_has_id_1(self, session):
        queries.upsert_user_profile(session, name="Sahil")
        profile = queries.get_user_profile(session)
        assert profile.id == 1


# ---------------------------------------------------------------------------
# user_health_profile
# ---------------------------------------------------------------------------

class TestUserHealthProfile:
    def test_insert_health_profile(self, session):
        queries.insert_health_profile(
            session,
            report_date="2026-05-01",
            a1c=6.4,
            ldl=142,
            hdl=45,
            triglycerides=150,
            medications=["metformin"],
            bmi=24.5,
        )
        row = queries.get_latest_health_profile(session)
        assert row is not None
        assert row.a1c == 6.4

    def test_get_latest_health_profile_none_when_empty(self, session):
        row = queries.get_latest_health_profile(session)
        assert row is None

    def test_get_latest_returns_most_recent(self, session):
        queries.insert_health_profile(
            session,
            report_date="2026-01-01",
            a1c=6.8,
            ldl=155,
            hdl=40,
            triglycerides=180,
            medications=[],
            bmi=25.0,
        )
        queries.insert_health_profile(
            session,
            report_date="2026-05-01",
            a1c=6.4,
            ldl=142,
            hdl=45,
            triglycerides=150,
            medications=["metformin"],
            bmi=24.5,
        )
        row = queries.get_latest_health_profile(session)
        assert row.report_date == "2026-05-01"
        assert row.a1c == 6.4

    def test_get_health_profile_trend_returns_all_in_order(self, session):
        for rd, a1c, ldl, hdl in [
            ("2025-11-01", 7.0, 160, 38),
            ("2026-01-01", 6.8, 155, 40),
            ("2026-05-01", 6.4, 142, 45),
        ]:
            queries.insert_health_profile(
                session,
                report_date=rd,
                a1c=a1c,
                ldl=ldl,
                hdl=hdl,
                triglycerides=150,
                medications=[],
                bmi=24.0,
            )
        trend = queries.get_health_profile_trend(session)
        assert len(trend) == 3
        assert trend[0][0] == "2025-11-01"
        assert trend[2][0] == "2026-05-01"

    def test_duplicate_report_date_raises_integrity_error(self, session):
        queries.insert_health_profile(
            session,
            report_date="2026-05-01",
            a1c=6.4,
            ldl=142,
            hdl=45,
            triglycerides=150,
            medications=[],
            bmi=24.5,
        )
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            queries.insert_health_profile(
                session,
                report_date="2026-05-01",
                a1c=6.2,
                ldl=138,
                hdl=47,
                triglycerides=145,
                medications=[],
                bmi=24.0,
            )

    def test_medications_is_parsed_list(self, session):
        queries.insert_health_profile(
            session,
            report_date="2026-05-01",
            a1c=6.4,
            ldl=142,
            hdl=45,
            triglycerides=150,
            medications=["metformin", "atorvastatin"],
            bmi=24.5,
        )
        row = queries.get_latest_health_profile(session)
        assert isinstance(row.medications, list)
        assert "metformin" in row.medications


# ---------------------------------------------------------------------------
# user_nutrition_guidance
# ---------------------------------------------------------------------------

class TestUserNutritionGuidance:
    def test_insert_guidance_rule_returns_id(self, session):
        rule_id = queries.insert_guidance_rule(
            session,
            rule="Limit carbs to 45g/meal given A1C 6.4%",
            category="a1c",
            source="health_profile",
            priority=1,
            source_lab_date="2026-05-01",
        )
        assert isinstance(rule_id, int)
        assert rule_id > 0

    def test_get_active_guidance_returns_only_active(self, session):
        queries.insert_guidance_rule(
            session,
            rule="Eat more fiber",
            category="general",
            source="knowledge_base",
            priority=2,
            source_lab_date=None,
        )
        rid = queries.insert_guidance_rule(
            session,
            rule="Reduce saturated fat",
            category="ldl",
            source="health_profile",
            priority=1,
            source_lab_date="2026-05-01",
        )
        queries.deactivate_guidance_rule(session, rid, remark="LDL normalized")

        active = queries.get_active_guidance(session)
        assert len(active) == 1
        assert active[0].rule == "Eat more fiber"

    def test_get_active_guidance_empty_when_none_active(self, session):
        rid = queries.insert_guidance_rule(
            session,
            rule="Some rule",
            category="general",
            source="knowledge_base",
            priority=1,
            source_lab_date=None,
        )
        queries.deactivate_guidance_rule(session, rid, remark="No longer relevant")
        active = queries.get_active_guidance(session)
        assert active == []

    def test_deactivate_guidance_rule(self, session):
        rid = queries.insert_guidance_rule(
            session,
            rule="Avoid high-GI foods",
            category="a1c",
            source="health_profile",
            priority=1,
            source_lab_date="2026-05-01",
        )
        queries.deactivate_guidance_rule(session, rid, remark="A1C improved")

        active = queries.get_active_guidance(session)
        assert not any(r.id == rid for r in active)

    def test_reactivate_guidance_rule(self, session):
        rid = queries.insert_guidance_rule(
            session,
            rule="Limit white rice",
            category="a1c",
            source="health_profile",
            priority=1,
            source_lab_date="2026-05-01",
        )
        queries.deactivate_guidance_rule(session, rid, remark="Temporarily relaxed")
        queries.reactivate_guidance_rule(session, rid)

        active = queries.get_active_guidance(session)
        assert any(r.id == rid for r in active)

    def test_reactivate_clears_remark_and_deactivated_at(self, session):
        from db.models import UserNutritionGuidance
        rid = queries.insert_guidance_rule(
            session,
            rule="Limit white rice",
            category="a1c",
            source="health_profile",
            priority=1,
            source_lab_date="2026-05-01",
        )
        queries.deactivate_guidance_rule(session, rid, remark="old remark")
        queries.reactivate_guidance_rule(session, rid)

        row = session.get(UserNutritionGuidance, rid)
        assert row.remark is None
        assert row.deactivated_at is None
        assert row.is_active == 1


# ---------------------------------------------------------------------------
# user_semantic_memory
# ---------------------------------------------------------------------------

class TestUserSemanticMemory:
    def _sample_facts(self):
        return [
            {
                "category": "meal_pattern",
                "fact": "Eats heavy dinners on weekends",
                "confidence": "strong",
                "evidence": json.dumps(["2026-06-14", "2026-06-15"]),
                "valid_from": "2026-03-01",
            },
            {
                "category": "sleep_pattern",
                "fact": "Averages 6.5 hrs sleep on weekdays",
                "confidence": "moderate",
                "evidence": json.dumps(["2026-06-16", "2026-06-17"]),
                "valid_from": "2026-03-01",
            },
        ]

    def test_replace_inserts_new_facts(self, session):
        queries.replace_semantic_memory(session, self._sample_facts())
        facts = queries.get_semantic_memory(session)
        assert len(facts) == 2

    def test_replace_deletes_old_facts_first(self, session):
        queries.replace_semantic_memory(session, self._sample_facts())
        new_facts = [
            {
                "category": "behavioral",
                "fact": "Exercises on Monday mornings",
                "confidence": "weak",
                "evidence": None,
                "valid_from": "2026-04-01",
            }
        ]
        queries.replace_semantic_memory(session, new_facts)
        facts = queries.get_semantic_memory(session)
        assert len(facts) == 1
        assert facts[0]["fact"] == "Exercises on Monday mornings"

    def test_replace_with_empty_list_clears_all(self, session):
        queries.replace_semantic_memory(session, self._sample_facts())
        queries.replace_semantic_memory(session, [])
        facts = queries.get_semantic_memory(session)
        assert facts == []

    def test_get_semantic_memory_returns_list_of_dicts(self, session):
        queries.replace_semantic_memory(session, self._sample_facts())
        facts = queries.get_semantic_memory(session)
        assert isinstance(facts, list)
        assert isinstance(facts[0], dict)
        assert "category" in facts[0]
        assert "fact" in facts[0]


# ---------------------------------------------------------------------------
# daily_summaries
# ---------------------------------------------------------------------------

class TestDailySummaries:
    def test_upsert_creates_summary(self, session):
        queries.upsert_daily_summary(
            session,
            date="2026-06-20",
            total_macros={"calories": 1800, "protein": 80, "carbs": 220, "fat": 60},
            dietary_score=78,
            improvements=[{"category": "a1c", "recommendation": "reduce white rice"}],
        )
        row = queries.get_daily_summary(session, "2026-06-20")
        assert row is not None
        assert row.dietary_score == 78

    def test_upsert_updates_existing_summary(self, session):
        queries.upsert_daily_summary(
            session,
            date="2026-06-20",
            total_macros={"calories": 1800},
            dietary_score=78,
            improvements=[],
        )
        queries.upsert_daily_summary(
            session,
            date="2026-06-20",
            total_macros={"calories": 2000},
            dietary_score=82,
            improvements=[{"category": "ldl", "recommendation": "less ghee"}],
        )
        row = queries.get_daily_summary(session, "2026-06-20")
        assert row.dietary_score == 82

    def test_get_daily_summary_none_when_missing(self, session):
        row = queries.get_daily_summary(session, "2099-01-01")
        assert row is None

    def test_total_macros_is_parsed_dict(self, session):
        queries.upsert_daily_summary(
            session,
            date="2026-06-20",
            total_macros={"calories": 1800, "protein": 80},
            dietary_score=78,
            improvements=[],
        )
        row = queries.get_daily_summary(session, "2026-06-20")
        assert isinstance(row.total_macros, dict)
        assert row.total_macros["calories"] == 1800


# ---------------------------------------------------------------------------
# weekly_reports
# ---------------------------------------------------------------------------

class TestWeeklyReports:
    def test_upsert_creates_report(self, session):
        queries.upsert_weekly_report(
            session,
            week_start="2026-06-15",
            avg_dietary_score=80,
            score_delta=5,
            patterns_detected=["high_gi_streak"],
            recommendations={"a1c": "reduce refined carbs"},
        )
        row = queries.get_weekly_report(session, "2026-06-15")
        assert row is not None
        assert row.avg_dietary_score == 80

    def test_upsert_updates_existing_report(self, session):
        queries.upsert_weekly_report(
            session,
            week_start="2026-06-15",
            avg_dietary_score=80,
            score_delta=5,
            patterns_detected=[],
            recommendations={},
        )
        queries.upsert_weekly_report(
            session,
            week_start="2026-06-15",
            avg_dietary_score=85,
            score_delta=10,
            patterns_detected=["low_protein"],
            recommendations={"general": "eat more legumes"},
        )
        row = queries.get_weekly_report(session, "2026-06-15")
        assert row.avg_dietary_score == 85

    def test_get_weekly_report_none_when_missing(self, session):
        row = queries.get_weekly_report(session, "2099-01-01")
        assert row is None

    def test_get_last_week_recommendations_none_when_no_reports(self, session):
        result = queries.get_last_week_recommendations(session)
        assert result is None

    def test_get_last_week_recommendations_returns_most_recent(self, session):
        queries.upsert_weekly_report(
            session,
            week_start="2026-06-08",
            avg_dietary_score=75,
            score_delta=0,
            patterns_detected=[],
            recommendations={"a1c": "reduce white rice"},
        )
        queries.upsert_weekly_report(
            session,
            week_start="2026-06-15",
            avg_dietary_score=80,
            score_delta=5,
            patterns_detected=[],
            recommendations={"ldl": "avoid ghee"},
        )
        rec = queries.get_last_week_recommendations(session)
        assert rec is not None
        assert isinstance(rec, dict)
        assert "ldl" in rec


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------

class TestPatterns:
    def test_insert_pattern(self, session):
        from datetime import datetime
        today = str(datetime.now(ZoneInfo("America/Los_Angeles")).date())
        queries.insert_pattern(
            session,
            date=today,
            pattern_type="high_gi_streak",
            streak_days=3,
        )
        rows = queries.get_patterns_last_7_days(session)
        assert len(rows) >= 1

    def test_get_patterns_last_7_days_returns_list(self, session):
        rows = queries.get_patterns_last_7_days(session)
        assert isinstance(rows, list)

    def test_get_sent_callouts_returns_pattern_types(self, session):
        queries.insert_pattern(
            session,
            date="2026-06-20",
            pattern_type="high_gi_streak",
            streak_days=3,
        )
        queries.insert_pattern(
            session,
            date="2026-06-20",
            pattern_type="low_protein",
            streak_days=4,
        )
        callouts = queries.get_sent_callouts(session, "2026-06-20")
        assert "high_gi_streak" in callouts
        assert "low_protein" in callouts

    def test_get_sent_callouts_empty_for_no_patterns(self, session):
        callouts = queries.get_sent_callouts(session, "2099-01-01")
        assert callouts == []

    def test_get_sent_callouts_filters_by_date(self, session):
        queries.insert_pattern(
            session,
            date="2026-06-19",
            pattern_type="high_gi_streak",
            streak_days=2,
        )
        callouts = queries.get_sent_callouts(session, "2026-06-20")
        assert "high_gi_streak" not in callouts


# ---------------------------------------------------------------------------
# indian_foods
# ---------------------------------------------------------------------------

class TestIndianFoods:
    def test_upsert_indian_food_creates_row(self, session):
        queries.upsert_indian_food(
            session,
            name="dal makhani",
            calories_per_100g=150.0,
            protein_g=8.0,
            carbs_g=18.0,
            fat_g=5.5,
            fiber_g=4.0,
            saturated_fat_g=2.0,
            sugar_g=2.0,
            glycemic_index=30,
            notes="varies with ghee quantity",
        )
        food = queries.get_indian_food_by_name(session, "dal makhani")
        assert food is not None
        assert food.calories_per_100g == 150.0

    def test_upsert_indian_food_updates_existing(self, session):
        queries.upsert_indian_food(
            session,
            name="tawa roti",
            calories_per_100g=260.0,
            protein_g=8.5,
            carbs_g=50.0,
            fat_g=3.5,
            fiber_g=3.0,
            saturated_fat_g=0.5,
            sugar_g=1.0,
            glycemic_index=62,
            notes=None,
        )
        queries.upsert_indian_food(
            session,
            name="tawa roti",
            calories_per_100g=265.0,
            protein_g=8.5,
            carbs_g=50.0,
            fat_g=3.5,
            fiber_g=3.0,
            saturated_fat_g=0.5,
            sugar_g=1.0,
            glycemic_index=62,
            notes="whole wheat",
        )
        food = queries.get_indian_food_by_name(session, "tawa roti")
        assert food.calories_per_100g == 265.0
        assert food.notes == "whole wheat"

    def test_get_indian_food_by_name_none_when_not_found(self, session):
        food = queries.get_indian_food_by_name(session, "nonexistent dish")
        assert food is None

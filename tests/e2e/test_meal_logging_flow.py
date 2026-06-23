"""
E2E tests for the meal logging flow.

Tests cover:
1. Photo message buffering — pure helpers work correctly
2. Multi-photo album buffering accumulates all photos before dispatch
3. DB save — save_meal_analysis tool (via queries) inserts a meal log row

These tests use the pure helper functions from bot.handlers.meal (no Telegram mocking needed
for buffer tests) and the queries layer directly (no agent invocation needed for DB tests).
"""

import pytest
from cachetools import TTLCache
from datetime import datetime
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")


# ---------------------------------------------------------------------------
# Buffer helper tests (pure functions, no Telegram context)
# ---------------------------------------------------------------------------

class TestPhotoBombBuffering:
    def test_single_photo_is_new_media_group(self):
        """is_new_media_group returns True for a fresh group id."""
        from bot.handlers.meal import is_new_media_group

        cache = TTLCache(maxsize=100, ttl=10)
        assert is_new_media_group("group-abc", cache) is True

    def test_buffer_photo_adds_file_id(self):
        """buffer_photo stores the file_id under the group key."""
        from bot.handlers.meal import buffer_photo, get_buffered_photos

        cache = TTLCache(maxsize=100, ttl=10)
        buffer_photo("group-1", "file-id-001", cache)

        photos = get_buffered_photos("group-1", cache)
        assert photos == ["file-id-001"]

    def test_multi_photo_buffering_accumulates(self):
        """Sending 3 photos with the same media_group_id buffers all 3."""
        from bot.handlers.meal import buffer_photo, get_buffered_photos, is_new_media_group

        cache = TTLCache(maxsize=100, ttl=10)
        group_id = "group-multi"
        file_ids = ["photo-1", "photo-2", "photo-3"]

        for i, fid in enumerate(file_ids):
            if i == 0:
                assert is_new_media_group(group_id, cache) is True
            buffer_photo(group_id, fid, cache)

        buffered = get_buffered_photos(group_id, cache)
        assert len(buffered) == 3
        assert set(buffered) == set(file_ids)

    def test_is_new_media_group_false_after_buffering(self):
        """After buffering, is_new_media_group returns False for the same group."""
        from bot.handlers.meal import buffer_photo, is_new_media_group

        cache = TTLCache(maxsize=100, ttl=10)
        group_id = "group-xyz"

        assert is_new_media_group(group_id, cache) is True
        buffer_photo(group_id, "file-1", cache)
        assert is_new_media_group(group_id, cache) is False

    def test_different_groups_are_independent(self):
        """Two different media group ids have independent buffers."""
        from bot.handlers.meal import buffer_photo, get_buffered_photos

        cache = TTLCache(maxsize=100, ttl=10)
        buffer_photo("group-A", "photo-A1", cache)
        buffer_photo("group-B", "photo-B1", cache)
        buffer_photo("group-B", "photo-B2", cache)

        assert get_buffered_photos("group-A", cache) == ["photo-A1"]
        assert get_buffered_photos("group-B", cache) == ["photo-B1", "photo-B2"]


# ---------------------------------------------------------------------------
# DB save tests — verify queries layer handles meal log insertion
# ---------------------------------------------------------------------------

class TestMealAnalysisSavesToDb:
    def test_meal_log_is_inserted(self, session):
        """save_meal_analysis route: queries.insert_meal_log persists a row."""
        from db import queries
        from db.models import MealLog
        from sqlalchemy import select

        today = datetime.now(LA).strftime("%Y-%m-%d")
        row_id = queries.insert_meal_log(
            session,
            date=today,
            meal_type="lunch",
            logged_at=f"{today}T13:00:00",
            foods_identified=["dal", "rice", "sabzi"],
            macros={
                "calories": 650,
                "protein_g": 22,
                "carbs_g": 95,
                "fat_g": 12,
                "fiber_g": 8,
            },
            flags={"high_fiber": True},
            score=8,
        )

        assert row_id is not None
        rows = session.execute(select(MealLog).where(MealLog.date == today)).scalars().all()
        assert len(rows) == 1
        assert rows[0].meal_type == "lunch"
        assert "dal" in rows[0].foods_identified

    def test_multiple_meals_same_day(self, session):
        """Multiple meal logs for the same day are all stored."""
        from db import queries
        from db.models import MealLog
        from sqlalchemy import select

        today = datetime.now(LA).strftime("%Y-%m-%d")
        for meal_type in ["breakfast", "lunch", "dinner"]:
            queries.insert_meal_log(
                session,
                date=today,
                meal_type=meal_type,
                logged_at=f"{today}T12:00:00",
                foods_identified=["test food"],
                macros={"calories": 400},
                flags={},
                score=7,
            )

        rows = session.execute(select(MealLog).where(MealLog.date == today)).scalars().all()
        assert len(rows) == 3
        meal_types = {r.meal_type for r in rows}
        assert meal_types == {"breakfast", "lunch", "dinner"}

    def test_meal_macros_stored_as_dict(self, session):
        """JSON macros column round-trips correctly through SQLAlchemy JSONType."""
        from db import queries
        from db.models import MealLog
        from sqlalchemy import select

        today = datetime.now(LA).strftime("%Y-%m-%d")
        macros = {"calories": 500, "protein_g": 30, "carbs_g": 60, "fat_g": 15, "fiber_g": 5}
        queries.insert_meal_log(
            session,
            date=today,
            meal_type="snack",
            logged_at=f"{today}T16:00:00",
            foods_identified=["peanut butter"],
            macros=macros,
            flags={},
            score=6,
        )

        row = session.execute(select(MealLog).where(MealLog.meal_type == "snack")).scalar_one()
        assert row.macros == macros

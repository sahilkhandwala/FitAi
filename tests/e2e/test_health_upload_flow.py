"""
E2E tests for the health PDF upload flow.

Tests cover:
1. Health profile is saved after extraction (queries layer)
2. Duplicate date is rejected (UNIQUE constraint on report_date)
3. Optional fields (hdl, triglycerides, bmi) accept None
4. Latest health profile is retrievable after insertion
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError

LA = ZoneInfo("America/Los_Angeles")


class TestHealthProfileSavedAfterExtraction:
    def test_health_profile_saved(self, session):
        """insert_health_profile persists a row retrievable via get_latest_health_profile."""
        from db import queries

        queries.insert_health_profile(
            session,
            report_date="2026-06-01",
            a1c=6.4,
            ldl=142,
            hdl=48,
            triglycerides=180,
            medications=["metformin 500mg"],
            bmi=25.6,
        )

        row = queries.get_latest_health_profile(session)
        assert row is not None
        assert row.report_date == "2026-06-01"
        assert row.a1c == 6.4
        assert row.ldl == 142

    def test_latest_returns_most_recent(self, session):
        """get_latest_health_profile returns the most recent report when multiple exist."""
        from db import queries

        queries.insert_health_profile(
            session,
            report_date="2026-01-01",
            a1c=6.8,
            ldl=155,
            hdl=42,
            triglycerides=200,
            medications=[],
            bmi=26.0,
        )
        queries.insert_health_profile(
            session,
            report_date="2026-06-01",
            a1c=6.2,
            ldl=130,
            hdl=52,
            triglycerides=160,
            medications=["metformin 500mg"],
            bmi=24.5,
        )

        row = queries.get_latest_health_profile(session)
        assert row.report_date == "2026-06-01"
        assert row.a1c == 6.2


class TestDuplicateDateRejected:
    def test_duplicate_report_date_raises_integrity_error(self, session):
        """Inserting two reports for the same date raises IntegrityError."""
        from db import queries

        queries.insert_health_profile(
            session,
            report_date="2026-06-15",
            a1c=6.5,
            ldl=145,
            hdl=45,
            triglycerides=190,
            medications=[],
            bmi=25.0,
        )

        with pytest.raises(IntegrityError):
            queries.insert_health_profile(
                session,
                report_date="2026-06-15",  # same date
                a1c=6.3,
                ldl=140,
                hdl=50,
                triglycerides=170,
                medications=[],
                bmi=24.8,
            )


class TestOptionalFieldsAcceptNone:
    def test_hdl_none_is_accepted(self, session):
        """HDL, triglycerides, and BMI can be None (partial lab report)."""
        from db import queries

        queries.insert_health_profile(
            session,
            report_date="2026-05-01",
            a1c=6.6,
            ldl=148,
            hdl=None,
            triglycerides=None,
            medications=["atorvastatin 10mg"],
            bmi=None,
        )

        row = queries.get_latest_health_profile(session)
        assert row is not None
        assert row.hdl is None
        assert row.triglycerides is None
        assert row.bmi is None
        assert row.a1c == 6.6

    def test_medications_can_be_empty_list(self, session):
        """Medications field accepts an empty list."""
        from db import queries

        queries.insert_health_profile(
            session,
            report_date="2026-04-01",
            a1c=6.0,
            ldl=120,
            hdl=55,
            triglycerides=140,
            medications=[],
            bmi=23.5,
        )

        row = queries.get_latest_health_profile(session)
        assert row.medications == []


class TestHealthProfileNoneWhenEmpty:
    def test_get_latest_returns_none_when_no_data(self, session):
        """get_latest_health_profile returns None when no rows exist."""
        from db import queries

        row = queries.get_latest_health_profile(session)
        assert row is None

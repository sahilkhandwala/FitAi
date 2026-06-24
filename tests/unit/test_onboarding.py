"""Unit tests for the onboarding module."""

import pytest


@pytest.fixture
def fresh_cache(tmp_path, monkeypatch):
    """Reset diskcache to a temp dir for each test."""
    import bot.cache as bc
    import diskcache

    # Replace the cache instance directly so get_app_cache() returns our temp cache.
    # Patching config.DISKCACHE_DIR alone won't work because bot.cache already
    # has its own binding of DISKCACHE_DIR captured at import time.
    bc._cache = diskcache.Cache(str(tmp_path / "cache"))
    yield
    bc._cache.close()
    bc._cache = None


def test_onboarding_needed_when_no_profile(session, fresh_cache):
    from bot.handlers.onboarding import is_onboarding_needed
    assert is_onboarding_needed(session) is True


def test_onboarding_not_needed_when_complete(session, fresh_cache):
    from bot.handlers.onboarding import is_onboarding_needed
    from bot.cache import set_onboarding_complete
    set_onboarding_complete()
    assert is_onboarding_needed(session) is False


def test_onboarding_not_needed_when_profile_exists(session, fresh_cache):
    from db.models import UserProfile
    from bot.handlers.onboarding import is_onboarding_needed
    p = UserProfile(id=1, name="Sahil", diet_type="omnivore")
    session.add(p)
    session.commit()
    assert is_onboarding_needed(session) is False


def test_save_onboarding_answers_writes_profile(session, fresh_cache):
    from bot.handlers.onboarding import save_onboarding_answers
    from db import queries

    answers = {
        "diet_type": "omnivore",
        "allergies": None,
        "activity_level": "moderate",
        "calorie_target": 1800,
    }
    save_onboarding_answers(session, answers)
    profile = queries.get_user_profile(session)
    assert profile is not None
    assert profile.diet_type == "omnivore"
    assert profile.calorie_target == 1800


def test_save_onboarding_answers_marks_complete(session, fresh_cache):
    from bot.handlers.onboarding import save_onboarding_answers
    from bot.cache import is_onboarding_complete

    save_onboarding_answers(session, {"diet_type": "vegan", "calorie_target": 1600})
    assert is_onboarding_complete() is True

"""Unit tests for bot/cache.py — diskcache singleton and interrupt helpers."""

import pytest


@pytest.fixture
def cache_instance(tmp_path, monkeypatch):
    """Patch DISKCACHE_DIR to a temp path so tests don't write to real cache."""
    monkeypatch.setattr("bot.cache.DISKCACHE_DIR", str(tmp_path / "cache"))
    # Force module-level singleton to reset between tests
    import bot.cache as bc
    bc._cache = None
    yield
    # Cleanup
    bc._cache = None


def test_get_app_cache_returns_cache(cache_instance):
    from bot.cache import get_app_cache
    import diskcache
    c = get_app_cache()
    assert isinstance(c, diskcache.Cache)


def test_get_app_cache_is_singleton(cache_instance):
    from bot.cache import get_app_cache
    assert get_app_cache() is get_app_cache()


def test_paused_agent_round_trip(cache_instance):
    from bot.cache import set_paused_agent, get_paused_agent, clear_paused_agent
    assert get_paused_agent() is None
    set_paused_agent("photo")
    assert get_paused_agent() == "photo"
    clear_paused_agent()
    assert get_paused_agent() is None


def test_onboarding_complete_default_false(cache_instance):
    from bot.cache import is_onboarding_complete
    assert is_onboarding_complete() is False


def test_onboarding_complete_set(cache_instance):
    from bot.cache import set_onboarding_complete, is_onboarding_complete
    set_onboarding_complete()
    assert is_onboarding_complete() is True


def test_onboarding_prompt_sent_default_false(cache_instance):
    from bot.cache import has_sent_onboarding_prompt
    assert has_sent_onboarding_prompt() is False


def test_onboarding_prompt_sent_set(cache_instance):
    from bot.cache import set_onboarding_prompt_sent, has_sent_onboarding_prompt
    set_onboarding_prompt_sent()
    assert has_sent_onboarding_prompt() is True

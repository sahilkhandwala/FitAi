"""
Shared diskcache.Cache singleton and interrupt/onboarding state helpers.

The Cache lives at DISKCACHE_DIR and survives bot restarts — used for:
  - paused_agent: which AGENT_REGISTRY trigger is currently interrupted
  - onboarding_complete: has user finished first-time setup
  - onboarding_prompt_sent: has the one-time lab-report tip been sent
"""

import diskcache
from config import DISKCACHE_DIR

_cache: diskcache.Cache | None = None

_KEY_PAUSED_AGENT = "paused_agent"
_KEY_ONBOARDING_COMPLETE = "onboarding_complete"
_KEY_ONBOARDING_PROMPT_SENT = "onboarding_prompt_sent"


def get_app_cache() -> diskcache.Cache:
    global _cache
    if _cache is None:
        _cache = diskcache.Cache(DISKCACHE_DIR)
    return _cache


def set_paused_agent(trigger: str) -> None:
    get_app_cache().set(_KEY_PAUSED_AGENT, trigger)


def get_paused_agent() -> str | None:
    return get_app_cache().get(_KEY_PAUSED_AGENT)


def clear_paused_agent() -> None:
    get_app_cache().delete(_KEY_PAUSED_AGENT)


def is_onboarding_complete() -> bool:
    return bool(get_app_cache().get(_KEY_ONBOARDING_COMPLETE, False))


def set_onboarding_complete() -> None:
    get_app_cache().set(_KEY_ONBOARDING_COMPLETE, True)


def has_sent_onboarding_prompt() -> bool:
    return bool(get_app_cache().get(_KEY_ONBOARDING_PROMPT_SENT, False))


def set_onboarding_prompt_sent() -> None:
    get_app_cache().set(_KEY_ONBOARDING_PROMPT_SENT, True)

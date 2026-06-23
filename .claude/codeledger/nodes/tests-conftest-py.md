# tests/conftest.py

## Summary
Shared pytest fixtures for the FitAi test suite. Sets up minimal env vars to prevent KeyError on config import, provides an in-memory SQLite engine with all 10 tables created (using StaticPool), a Session fixture, a knowledge_base_dir fixture with 2 sample JSON articles, and optional mock fixtures for Anthropic, Fitbit, and weather APIs.

## Functions
- db(scope=function) — fixture; creates in-memory SQLite engine with Base.metadata.create_all, WAL pragma (no-op on memory), yields engine
- session(db) — fixture; SessionFactory bound to test engine, yields session, closes on teardown
- knowledge_base_dir(tmp_path) — fixture; creates tmp knowledge_base/ dir with 2 JSON files (fiber_a1c.json, omega3_hdl.json)
- mock_anthropic(monkeypatch) — fixture; patches both langchain_anthropic.ChatAnthropic AND bot.agents.base_agent.ChatAnthropic with FakeChatAnthropic stub (has bind_tools returning self, invoke returning AIMessage); skips if not installed; double-patch ensures interception regardless of import order
- mock_fitbit(monkeypatch) — fixture; patches requests.get with FakeResponse returning sample Fitbit data
- mock_weather(monkeypatch) — fixture; patches openmeteo_requests.Client; skips if not installed

## Non-function code
- env var defaults set via os.environ.setdefault for TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY, SQLITE_DB_PATH

## Imports
- json, os, pytest
- sqlalchemy (create_engine, event), sqlalchemy.orm.sessionmaker, sqlalchemy.pool.StaticPool

## Imported by
- All test files in tests/ — fixtures are auto-discovered by pytest

## Tags
tests, fixtures, conftest, db, mocks

## Node path
tests/conftest.py

"""
Shared pytest fixtures for FitAi test suite.

Key design decisions:
- Uses StaticPool so create_all and sessions share one in-memory connection
- Does NOT import config (avoids mandatory env var KeyErrors at collection time)
- Mock fixtures do lazy imports inside fixture bodies (optional deps may not be installed)
"""

import json
import os
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Provide minimal env vars so config.py can be imported by other modules without KeyError
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("SQLITE_DB_PATH", ":memory:")


@pytest.fixture(scope="function")
def db():
    """
    In-memory SQLite engine with all 10 tables created.
    Uses StaticPool so all connections share the same in-memory DB.
    WAL pragma is a no-op on :memory: (returns 'memory') — that's fine.
    """
    from db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_wal(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def session(db):
    """SQLAlchemy Session bound to the in-memory test engine."""
    SessionFactory = sessionmaker(bind=db, autoflush=False)
    s = SessionFactory()
    yield s
    s.close()


@pytest.fixture
def knowledge_base_dir(tmp_path):
    """
    Temp directory with 2 sample knowledge base JSON files.
    Schema: {source, ingested_at, relevance_tags, findings}
    """
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()

    article_1 = {
        "source": "Effect of dietary fiber on A1C — Smith et al. 2025",
        "ingested_at": "2026-01-01",
        "relevance_tags": ["a1c", "fiber"],
        "findings": [
            "High dietary fiber intake (>30g/day) reduces A1C by 0.3-0.5% over 12 weeks.",
            "Soluble fiber from oats and legumes shows strongest effect on glycemic control.",
        ],
    }
    article_2 = {
        "source": "Omega-3 and HDL cholesterol — Patel et al. 2025",
        "ingested_at": "2026-01-15",
        "relevance_tags": ["hdl", "ldl"],
        "findings": [
            "Omega-3 supplementation raises HDL by 4-8% in sedentary adults.",
            "EPA+DHA from fatty fish more effective than ALA from flaxseed.",
        ],
    }

    (kb_dir / "fiber_a1c.json").write_text(json.dumps(article_1))
    (kb_dir / "omega3_hdl.json").write_text(json.dumps(article_2))

    return kb_dir


@pytest.fixture
def mock_anthropic(monkeypatch):
    """Monkeypatch langchain_anthropic.ChatAnthropic with a minimal stub."""
    try:
        import langchain_anthropic  # noqa: F401
    except ImportError:
        pytest.skip("langchain_anthropic not installed")

    from langchain_core.messages import AIMessage

    class FakeChatAnthropic:
        def __init__(self, *args, **kwargs):
            self.model = kwargs.get("model", "stub")

        def bind_tools(self, tools, **kwargs):
            """Return self so tool-binding agents can still call invoke."""
            return self

        def invoke(self, messages, **kwargs):
            # Return a real AIMessage so LangGraph tools_condition can inspect tool_calls
            return AIMessage(content="stub response")

        def stream(self, messages, **kwargs):
            yield AIMessage(content="stub")

    # Patch where it's used (imported reference), not just where it's defined.
    # base_agent.py does `from langchain_anthropic import ChatAnthropic` at import time,
    # so we must patch the bound name in that module to reliably intercept all instances.
    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", FakeChatAnthropic)
    monkeypatch.setattr("bot.agents.base_agent.ChatAnthropic", FakeChatAnthropic)
    return FakeChatAnthropic


@pytest.fixture
def mock_health_api(monkeypatch):
    """Monkeypatch requests.post for Google Health API calls."""
    import requests

    class FakeStepsResponse:
        status_code = 200

        def json(self):
            return {
                "rollupDataPoints": [
                    {"civilStartTime": {"year": 2026, "month": 6, "day": 22}, "steps": {"count_sum": 8000}}
                ]
            }

        def raise_for_status(self):
            pass

    class FakeSleepResponse:
        status_code = 200

        def json(self):
            return {
                "rollupDataPoints": [
                    {"civilStartTime": {"year": 2026, "month": 6, "day": 22}, "sleep": {"totalSleepMinutes": 420}}
                ]
            }

        def raise_for_status(self):
            pass

    def fake_post(url, **kwargs):
        if "steps" in url:
            return FakeStepsResponse()
        return FakeSleepResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    return fake_post


@pytest.fixture
def mock_weather(monkeypatch):
    """Monkeypatch openmeteo_requests for Open-Meteo responses."""
    try:
        import openmeteo_requests  # noqa: F401
    except ImportError:
        pytest.skip("openmeteo_requests not installed")

    class FakeWeatherResponse:
        def Current(self):
            class Current:
                def Variables(self, i):
                    class Var:
                        Value = lambda self: 72.0  # noqa: E731

                    return Var()

            return Current()

    class FakeClient:
        def weather_api(self, url, params):
            return [FakeWeatherResponse()]

    monkeypatch.setattr("openmeteo_requests.Client", lambda *a, **kw: FakeClient())
    return FakeClient

"""
Integration tests for flows/morning_report.py.

All external calls (Google Health API, weather, Claude, Telegram) are mocked.
Prefect test harness is used so flows run inline without a real server.
"""

import pytest
from unittest.mock import MagicMock, patch
from prefect.testing.utilities import prefect_test_harness


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_llm(monkeypatch):
    """Stub ChatAnthropic so no real API call is made."""
    from langchain_core.messages import AIMessage

    class FakeLLM:
        def __init__(self, *args, **kwargs):
            pass

        def invoke(self, messages, **kwargs):
            return AIMessage(content="Good morning! ☀️ Stub morning message.")

    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", FakeLLM)
    monkeypatch.setattr("flows.morning_report.ChatAnthropic", FakeLLM)
    return FakeLLM


def _make_health_api_post(steps=8000, sleep_minutes=420):
    """Return a fake requests.post that mimics Google Health API dailyRollUp responses."""
    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "steps" in url:
            resp.json.return_value = {
                "rollupDataPoints": [{"steps": {"count_sum": steps}}]
            }
        elif "sleep" in url:
            resp.json.return_value = {
                "rollupDataPoints": [{"sleep": {"totalSleepMinutes": sleep_minutes}}]
            }
        else:
            # Telegram sendMessage or other POST
            resp.json.return_value = {}
        return resp
    return fake_post


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchHealthData:
    def test_fetch_health_data_returns_steps_and_sleep(self, monkeypatch, tmp_path):
        """fetch_health_data task parses Google Health API dailyRollUp responses."""
        import diskcache
        import time

        cache = diskcache.Cache(str(tmp_path / "cache"))
        cache["health_api_token"] = {
            "access_token": "fake-token",
            "refresh_token": "fake-refresh",
            "expires_at": time.time() + 3600,
        }

        monkeypatch.setattr("flows.morning_report.DISKCACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setattr("requests.post", _make_health_api_post(steps=8000, sleep_minutes=420))

        with prefect_test_harness():
            from flows.morning_report import fetch_health_data
            result = fetch_health_data.fn("2026-06-21")

        assert result["steps"] == 8000
        assert result["sleep_minutes"] == 420

    def test_fetch_health_data_no_token_returns_zeros(self, monkeypatch, tmp_path):
        """fetch_health_data returns zero data when no token is in cache."""
        import diskcache

        diskcache.Cache(str(tmp_path / "cache"))  # empty cache
        monkeypatch.setattr("flows.morning_report.DISKCACHE_DIR", str(tmp_path / "cache"))

        with prefect_test_harness():
            from flows.morning_report import fetch_health_data
            result = fetch_health_data.fn("2026-06-21")

        assert result == {"steps": 0, "sleep_minutes": 0}


class TestFetchWeather:
    def test_morning_report_fetches_weather(self, monkeypatch):
        """fetch_weather task retrieves weather data from Open-Meteo mock."""
        try:
            import openmeteo_requests  # noqa: F401
        except ImportError:
            pytest.skip("openmeteo_requests not installed")

        class FakeVar:
            def __init__(self, value):
                self._value = value

            def Value(self):
                return self._value

        class FakeCurrent:
            def Variables(self, i):
                return FakeVar([72.5, 1][i])  # temp=72.5, weathercode=1

        class FakeWeatherResponse:
            def Current(self):
                return FakeCurrent()

        class FakeClient:
            def weather_api(self, url, params):
                return [FakeWeatherResponse()]

        monkeypatch.setattr("openmeteo_requests.Client", lambda *a, **kw: FakeClient())
        # Patch requests_cache and retry_requests to avoid disk access
        import types
        fake_cache_session = MagicMock()
        monkeypatch.setattr("requests_cache.CachedSession", lambda *a, **kw: fake_cache_session)
        monkeypatch.setattr("retry_requests.retry", lambda s, **kw: s)

        with prefect_test_harness():
            from flows.morning_report import fetch_weather
            result = fetch_weather.fn()

        assert "temp_f" in result
        assert "condition" in result
        assert "rain_expected" in result
        assert result["temp_f"] == 72.5
        assert result["rain_expected"] is False


class TestSendTelegram:
    def test_morning_report_sends_telegram(self, monkeypatch):
        """send_telegram task calls the Telegram bot API with correct URL and chat_id."""
        posted = {}

        def fake_post(url, json=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr("requests.post", fake_post)

        with prefect_test_harness():
            from flows.morning_report import send_telegram
            send_telegram.fn("Good morning test message")

        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        assert TELEGRAM_BOT_TOKEN in posted["url"]
        assert posted["json"]["chat_id"] == TELEGRAM_CHAT_ID
        assert "Good morning test message" in posted["json"]["text"]


class TestMorningReportFlowEndToEnd:
    def test_morning_report_flow_end_to_end(self, monkeypatch, tmp_path):
        """
        Full flow run with all external calls mocked.
        Verifies the flow completes without raising.
        """
        try:
            import openmeteo_requests  # noqa: F401
        except ImportError:
            pytest.skip("openmeteo_requests not installed")

        import diskcache
        import time

        # Set up fake diskcache token
        cache = diskcache.Cache(str(tmp_path / "cache"))
        cache["health_api_token"] = {
            "access_token": "fake-token",
            "refresh_token": "fake-refresh",
            "expires_at": time.time() + 3600,
        }
        monkeypatch.setattr("flows.morning_report.DISKCACHE_DIR", str(tmp_path / "cache"))

        # Mock Open-Meteo
        class FakeVar:
            def __init__(self, v):
                self._v = v

            def Value(self):
                return self._v

        class FakeCurrent:
            def Variables(self, i):
                return FakeVar([68.0, 0][i])

        class FakeWeatherResponse:
            def Current(self):
                return FakeCurrent()

        class FakeClient:
            def weather_api(self, url, params):
                return [FakeWeatherResponse()]

        monkeypatch.setattr("openmeteo_requests.Client", lambda *a, **kw: FakeClient())
        fake_cache_session = MagicMock()
        monkeypatch.setattr("requests_cache.CachedSession", lambda *a, **kw: fake_cache_session)
        monkeypatch.setattr("retry_requests.retry", lambda s, **kw: s)

        # Mock Claude
        _make_fake_llm(monkeypatch)

        # Mock all POST calls: Google Health API + Telegram
        post_calls = []

        def fake_post(url, json=None, headers=None, data=None, timeout=None, **kwargs):
            post_calls.append({"url": url, "json": json})
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            if "steps" in url:
                resp.json.return_value = {"rollupDataPoints": [{"steps": {"count_sum": 7500}}]}
            elif "sleep" in url:
                resp.json.return_value = {"rollupDataPoints": [{"sleep": {"totalSleepMinutes": 450}}]}
            else:
                resp.json.return_value = {}
            return resp

        monkeypatch.setattr("requests.post", fake_post)

        with prefect_test_harness():
            from flows.morning_report import morning_report_flow
            # Should not raise
            morning_report_flow()

        # Verify Telegram was called
        assert len(post_calls) >= 1
        telegram_calls = [c for c in post_calls if "sendMessage" in c["url"]]
        assert len(telegram_calls) >= 1

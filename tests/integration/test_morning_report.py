"""
Integration tests for flows/morning_report.py.

All external calls (Fitbit, weather, Claude, Telegram) are mocked.
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


def _fake_fitbit_response():
    """Return a mock requests.Response for Fitbit API calls."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.side_effect = [
        # steps endpoint
        {"activities-steps": [{"dateTime": "2026-06-21", "value": "8000"}]},
        # sleep endpoint
        {"sleep": {"summary": {"totalTimeInBed": 420}}},
    ]
    return resp


def _fake_requests_post_ok():
    """Return a mock that simulates a successful Telegram sendMessage."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchFitbitData:
    def test_morning_report_fetches_fitbit_data(self, monkeypatch, tmp_path):
        """fetch_fitbit_data task runs without error when Fitbit API returns data."""
        import diskcache

        # Put a fake token in a temp diskcache
        cache = diskcache.Cache(str(tmp_path / "cache"))
        cache["fitbit_token"] = {"access_token": "fake-token"}

        monkeypatch.setenv("DISKCACHE_DIR", str(tmp_path / "cache"))
        # Patch config.DISKCACHE_DIR used in flow
        monkeypatch.setattr("flows.morning_report.DISKCACHE_DIR", str(tmp_path / "cache"))

        get_mock = MagicMock(side_effect=_fake_fitbit_response().json.side_effect)
        step_resp = MagicMock()
        step_resp.raise_for_status = MagicMock()
        step_resp.json.return_value = {
            "activities-steps": [{"dateTime": "2026-06-21", "value": "8000"}]
        }
        sleep_resp = MagicMock()
        sleep_resp.raise_for_status = MagicMock()
        sleep_resp.json.return_value = {"sleep": {"summary": {"totalTimeInBed": 420}}}

        call_count = [0]

        def fake_get(url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return step_resp
            return sleep_resp

        monkeypatch.setattr("requests.get", fake_get)

        with prefect_test_harness():
            from flows.morning_report import fetch_fitbit_data
            result = fetch_fitbit_data.fn("2026-06-21")

        assert result["steps"] == 8000
        assert result["sleep_minutes"] == 420


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

        # Set up fake diskcache token
        cache = diskcache.Cache(str(tmp_path / "cache"))
        cache["fitbit_token"] = {"access_token": "fake-token"}
        monkeypatch.setattr("flows.morning_report.DISKCACHE_DIR", str(tmp_path / "cache"))

        # Mock Fitbit requests.get
        step_resp = MagicMock()
        step_resp.raise_for_status = MagicMock()
        step_resp.json.return_value = {
            "activities-steps": [{"dateTime": "2026-06-21", "value": "7500"}]
        }
        sleep_resp = MagicMock()
        sleep_resp.raise_for_status = MagicMock()
        sleep_resp.json.return_value = {"sleep": {"summary": {"totalTimeInBed": 450}}}

        call_count = [0]

        def fake_get(url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return step_resp
            return sleep_resp

        monkeypatch.setattr("requests.get", fake_get)

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

        # Mock Telegram
        post_calls = []

        def fake_post(url, json=None, timeout=None):
            post_calls.append({"url": url, "json": json})
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
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

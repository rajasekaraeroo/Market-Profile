import datetime as dt
import json
from pathlib import Path

import pytest

from src.data import historical

FIXTURES_DIR = Path("tests/fixtures/upstox")


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(historical, "CACHE_DIR", cache_dir)
    yield cache_dir


def test_fetch_returns_dataframe_with_expected_shape(monkeypatch):
    payload = json.loads(
        (FIXTURES_DIR / "historical_candles_nifty.json").read_text()
    )
    calls = []

    def fake_get(url, headers, timeout=None):
        calls.append(url)
        return FakeResponse(payload)

    monkeypatch.setattr(historical.requests, "get", fake_get)

    result = historical.fetch_historical_session(
        "NSE_INDEX|Nifty 50", dt.date.today(), access_token="fake-token"
    )

    assert len(calls) == 1
    assert not result.is_partial_or_missing
    assert list(result.df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(result.df) == 2
    # Sorted ascending by timestamp despite API returning newest-first.
    assert result.df.index.is_monotonic_increasing


def test_holiday_or_missing_date_returns_flagged_empty_result(monkeypatch):
    payload = json.loads((FIXTURES_DIR / "historical_candles_empty.json").read_text())

    monkeypatch.setattr(
        historical.requests, "get", lambda url, headers, timeout=None: FakeResponse(payload)
    )

    result = historical.fetch_historical_session(
        "NSE_INDEX|Nifty 50", dt.date.today(), access_token="fake-token"
    )

    assert result.is_partial_or_missing
    assert result.df.empty


def test_second_call_for_same_date_hits_cache_not_api(monkeypatch):
    payload = json.loads(
        (FIXTURES_DIR / "historical_candles_nifty.json").read_text()
    )
    call_count = {"n": 0}

    def fake_get(url, headers, timeout=None):
        call_count["n"] += 1
        return FakeResponse(payload)

    monkeypatch.setattr(historical.requests, "get", fake_get)

    date = dt.date.today()
    historical.fetch_historical_session("NSE_INDEX|Nifty 50", date, access_token="x")
    historical.fetch_historical_session("NSE_INDEX|Nifty 50", date, access_token="x")

    assert call_count["n"] == 1


def test_request_beyond_lookback_window_raises():
    too_old = dt.date.today() - dt.timedelta(days=365)
    with pytest.raises(ValueError):
        historical.fetch_historical_session(
            "NSE_INDEX|Nifty 50", too_old, access_token="x"
        )

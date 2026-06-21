"""Historical 1-minute OHLC candles for backtesting Session 1's engine.

Fetches from Upstox's v3 historical-candle API
(`/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}`),
caches each session locally, and returns data in exactly the shape Session
1's `MarketProfile` expects: a DataFrame indexed by IST timestamp with
`open, high, low, close` columns (optionally `volume`).

NOT NETWORK-VERIFIED: this was built without live access to Upstox's API
to confirm response shape, so `_parse_candles_response` documents the
assumed schema inline. Verify against a real response before trusting this
in production.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

HISTORICAL_CANDLE_URL = (
    "https://api.upstox.com/v3/historical-candle/{instrument_key}/"
    "minutes/1/{to_date}/{from_date}"
)

CACHE_DIR = Path("data/cache")

# Upstox documents 1-minute historical candles as only available for a
# recent trailing window (not arbitrary history). Verify the exact limit
# against current docs; this is a conservative placeholder.
MAX_1MIN_LOOKBACK_DAYS = 30


@dataclass
class HistoricalSessionResult:
    df: pd.DataFrame
    is_partial_or_missing: bool


def _cache_path(instrument_key: str, date: dt.date) -> Path:
    safe_key = instrument_key.replace("|", "_").replace(" ", "_")
    return CACHE_DIR / f"{safe_key}_{date.isoformat()}.csv"


def _parse_candles_response(payload: dict) -> pd.DataFrame:
    """Upstox candle rows are documented as
    [timestamp, open, high, low, close, volume, open_interest], newest
    first, with timestamp as an ISO8601 string including the +05:30 IST
    offset.
    """
    candles = payload.get("data", {}).get("candles", [])
    if not candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    rows = []
    for candle in candles:
        timestamp, open_, high, low, close, volume = candle[:6]
        rows.append(
            {
                "timestamp": pd.Timestamp(timestamp).tz_convert("Asia/Kolkata"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    df.index = df.index.tz_localize(None)  # engine expects naive IST timestamps
    return df


def fetch_historical_session(
    instrument_key: str,
    date: dt.date,
    access_token: str,
    use_cache: bool = True,
) -> HistoricalSessionResult:
    """Fetch (or load from cache) 1-minute candles for one session date.

    Returns `is_partial_or_missing=True` if no candles came back (holiday
    or no data yet for that date) instead of raising — callers decide how
    to handle a missing session.
    """
    today = dt.date.today()
    if (today - date).days > MAX_1MIN_LOOKBACK_DAYS:
        raise ValueError(
            f"Requested date {date} is beyond Upstox's 1-minute historical "
            f"lookback window (~{MAX_1MIN_LOOKBACK_DAYS} days). "
            "Upstox does not serve arbitrary history at 1-minute granularity."
        )

    cache_path = _cache_path(instrument_key, date)
    if use_cache and cache_path.exists():
        df = pd.read_csv(cache_path, index_col="timestamp", parse_dates=True)
        return HistoricalSessionResult(df=df, is_partial_or_missing=df.empty)

    url = HISTORICAL_CANDLE_URL.format(
        instrument_key=instrument_key,
        to_date=date.isoformat(),
        from_date=date.isoformat(),
    )
    response = requests.get(
        url, headers={"Authorization": f"Bearer {access_token}"}
    )
    response.raise_for_status()
    df = _parse_candles_response(response.json())

    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_path, index_label="timestamp")

    return HistoricalSessionResult(df=df, is_partial_or_missing=df.empty)

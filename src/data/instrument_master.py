"""Upstox instrument master — the authoritative source for resolving an
F&O stock symbol to its instrument key, lot size, and strike interval,
instead of hand-maintaining a lookup table per stock (which is what
Session 2 did for the three indices, and which doesn't scale to an
open-ended watchlist).

Upstox publishes a daily instrument master file (documented at
https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz).
This module downloads it, caches it locally, and refreshes once per day
— instrument lists, lot sizes and strike intervals do change over time
(NSE/BSE circulars), so an indefinite cache would silently go stale.

NOT NETWORK-VERIFIED: this build environment has no outbound network
access, so the exact JSON schema below (field names, F&O segment marker,
how strike interval is expressed) follows Upstox's publicly documented
instrument master format rather than a freshly downloaded file. Per the
session spec's explicit caveat, do not trust these field names for a live
go-live without re-checking a real downloaded file first — flagging that
here rather than silently assuming the schema is exactly right.
"""

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import requests

INSTRUMENT_MASTER_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
)

CACHE_FILE = Path(
    os.environ.get("UPSTOX_INSTRUMENT_MASTER_CACHE", "data/cache/instrument_master.json")
)
CACHE_REFRESH_HOURS = 24

# F&O segment marker used by Upstox for NSE derivatives. SENSEX/BSE F&O
# stocks would use a different segment — not exercised by this build
# since the watchlist is NSE-equity-derivatives focused; flag if BSE
# stock F&O support is needed later.
FNO_SEGMENT = "NSE_FO"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StockConfig:
    symbol: str
    instrument_key: str
    lot_size: int
    strike_interval: float
    fno_eligible: bool


def _cache_is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = dt.datetime.now() - dt.datetime.fromtimestamp(path.stat().st_mtime)
    return age < dt.timedelta(hours=CACHE_REFRESH_HOURS)


def download_instrument_master() -> list[dict]:
    """Fetch the raw instrument master entries from Upstox.

    Returns the parsed JSON list as-is; callers index it by symbol.
    """
    response = requests.get(INSTRUMENT_MASTER_URL, timeout=30)
    response.raise_for_status()
    return response.json()


def _load_cached(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries))


def get_instrument_master(force_refresh: bool = False) -> list[dict]:
    """Return the instrument master entries, using the local cache unless
    it's missing, stale (> CACHE_REFRESH_HOURS old), or `force_refresh`."""
    if not force_refresh and _cache_is_fresh(CACHE_FILE):
        cached = _load_cached(CACHE_FILE)
        if cached is not None:
            return cached

    entries = download_instrument_master()
    _save_cache(CACHE_FILE, entries)
    return entries


def _find_fno_entry(entries: list[dict], symbol: str) -> dict | None:
    symbol = symbol.upper()
    for entry in entries:
        if entry.get("segment") != FNO_SEGMENT:
            continue
        if entry.get("name", "").upper() == symbol or entry.get(
            "trading_symbol", ""
        ).upper().startswith(symbol):
            return entry
    return None


def is_fno_eligible(symbol: str, entries: list[dict] | None = None) -> bool:
    entries = entries if entries is not None else get_instrument_master()
    return _find_fno_entry(entries, symbol) is not None


def get_stock_config(symbol: str, entries: list[dict] | None = None) -> StockConfig:
    """Resolve a watchlisted stock symbol to its instrument key, lot size,
    and strike interval, via the instrument master.

    Raises ValueError if the symbol isn't F&O-eligible — callers (the
    watchlist loader) must surface this clearly rather than skip it.
    """
    entries = entries if entries is not None else get_instrument_master()
    entry = _find_fno_entry(entries, symbol)
    if entry is None:
        raise ValueError(
            f"'{symbol}' is not F&O-eligible per the Upstox instrument master "
            "(or was not found at all). Remove it from config/watchlist.yaml "
            "or verify the symbol spelling."
        )

    return StockConfig(
        symbol=symbol.upper(),
        instrument_key=entry["instrument_key"],
        lot_size=int(entry["lot_size"]),
        strike_interval=float(entry["strike_interval"]),
        fno_eligible=True,
    )

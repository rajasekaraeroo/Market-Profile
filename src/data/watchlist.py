"""Loads and validates the user-editable stock watchlist
(`config/watchlist.yaml`) against the Upstox instrument master.

Every symbol in the watchlist must be F&O-eligible; an invalid symbol is
a hard error at load time (the spec is explicit: reject and clearly
report, don't silently skip).

Upstox WebSocket plans cap concurrent live subscriptions, and each
watchlisted stock needs both an equity-price subscription and option
chain polling — so the watchlist size itself is capped too.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.data.instrument_master import StockConfig, get_stock_config

DEFAULT_WATCHLIST_PATH = Path("config/watchlist.yaml")

# Default cap on concurrent watchlisted stocks, independent of the
# indices (NIFTY/BANKNIFTY/SENSEX always run). Tune via
# `load_watchlist(max_size=...)` rather than editing this constant for a
# one-off plan change.
MAX_WATCHLIST_SIZE = 20


class WatchlistError(ValueError):
    """Raised when the watchlist file is invalid: too large, or contains
    a symbol that isn't F&O-eligible."""


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    config: StockConfig


def _read_symbols(path: Path) -> list[str]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text()) or {}
    symbols = raw.get("stocks") or []
    return [s.upper() for s in symbols]


def load_watchlist(
    path: Path = DEFAULT_WATCHLIST_PATH,
    max_size: int = MAX_WATCHLIST_SIZE,
    entries: list[dict] | None = None,
) -> list[WatchlistEntry]:
    """Read, validate, and resolve every symbol in the watchlist file.

    `entries` lets callers (tests) pass a pre-fetched instrument master
    instead of hitting the network/cache for each symbol lookup.

    Raises WatchlistError if the list exceeds `max_size`, or if any
    symbol fails F&O-eligibility resolution.
    """
    symbols = _read_symbols(path)

    if len(symbols) > max_size:
        raise WatchlistError(
            f"Watchlist has {len(symbols)} symbols, exceeding the configured "
            f"max of {max_size}. Each watchlisted stock needs its own live "
            "subscription + option chain polling slot — trim the list in "
            f"{path}."
        )

    resolved: list[WatchlistEntry] = []
    errors: list[str] = []
    for symbol in symbols:
        try:
            config = get_stock_config(symbol, entries=entries)
            resolved.append(WatchlistEntry(symbol=symbol, config=config))
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise WatchlistError(
            "Watchlist contains symbol(s) that failed validation:\n"
            + "\n".join(errors)
        )

    return resolved

"""Instrument configuration for Market Profile computation.

Each instrument has its own value_step (TPO row size), session times, TPO
period length, and number of periods that make up the Initial Balance.
Adding a new instrument is a matter of adding one entry to INSTRUMENTS —
the engine itself must never hardcode instrument-specific behavior.
"""

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class InstrumentConfig:
    key: str
    exchange: str
    value_step: float
    market_open: time
    market_close: time
    tpo_period_minutes: int
    ib_periods: int


INSTRUMENTS: dict[str, InstrumentConfig] = {
    "NIFTY": InstrumentConfig(
        key="NIFTY",
        exchange="NSE",
        value_step=25,
        market_open=time(9, 15),
        market_close=time(15, 30),
        tpo_period_minutes=30,
        ib_periods=2,
    ),
    "BANKNIFTY": InstrumentConfig(
        key="BANKNIFTY",
        exchange="NSE",
        value_step=100,
        market_open=time(9, 15),
        market_close=time(15, 30),
        tpo_period_minutes=30,
        ib_periods=2,
    ),
    "SENSEX": InstrumentConfig(
        key="SENSEX",
        exchange="BSE",
        value_step=100,
        market_open=time(9, 15),
        market_close=time(15, 30),
        tpo_period_minutes=30,
        ib_periods=2,
    ),
}


def get_instrument_config(instrument_key: str) -> InstrumentConfig:
    try:
        return INSTRUMENTS[instrument_key.upper()]
    except KeyError:
        raise ValueError(
            f"Unknown instrument '{instrument_key}'. "
            f"Available: {sorted(INSTRUMENTS)}"
        )


def register_stock_instrument(symbol: str, strike_interval: float) -> InstrumentConfig:
    """Register a watchlisted F&O stock as an instrument, deriving its
    `value_step` from the stock's actual exchange-published strike
    interval (via `instrument_master.py`) rather than a hardcoded
    price-tier table — strike intervals are the most defensible default
    since NSE/BSE already define them per-stock.

    Session times / TPO period / IB periods are shared with the indices:
    nothing in tpo.py or day_type.py reads instrument-specific behavior
    beyond `InstrumentConfig` fields, so stocks need no engine changes —
    confirmed by the existing Session 1 tests passing unmodified.
    """
    symbol = symbol.upper()
    config = InstrumentConfig(
        key=symbol,
        exchange="NSE",
        value_step=strike_interval,
        market_open=time(9, 15),
        market_close=time(15, 30),
        tpo_period_minutes=30,
        ib_periods=2,
    )
    INSTRUMENTS[symbol] = config
    return config

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

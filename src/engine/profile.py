"""Top-level orchestration: ties instrument config, TPO, and day-type
classification together into a single `MarketProfile` result.

Works equally for a complete session or a partial/mid-session DataFrame —
pass in whatever data is available and `.compute()` will produce the best
profile it can from it (this is what lets later sessions feed it live data
period by period).
"""

from dataclasses import dataclass

import pandas as pd

from src.engine.day_type import DayTypeResult, classify_day_type
from src.engine.instruments import get_instrument_config
from src.engine.tpo import TPOProfile, build_tpo_profile


@dataclass
class ProfileResult:
    instrument_key: str
    tpo: TPOProfile
    day_type: DayTypeResult

    @property
    def poc(self) -> float:
        return self.tpo.poc

    @property
    def va_high(self) -> float:
        return self.tpo.va_high

    @property
    def va_low(self) -> float:
        return self.tpo.va_low

    @property
    def ib_high(self) -> float:
        return self.day_type.ib_high

    @property
    def ib_low(self) -> float:
        return self.day_type.ib_low


class MarketProfile:
    """Computes a Market Profile for one instrument over one session
    (or partial session) of 1-minute OHLC data."""

    def __init__(self, instrument_key: str, df: pd.DataFrame):
        self.instrument_key = instrument_key
        self.config = get_instrument_config(instrument_key)
        self.df = df

    def compute(self) -> ProfileResult:
        tpo_profile = build_tpo_profile(self.df, self.config)
        day_type_result = classify_day_type(
            self.df, tpo_profile.period_letters, self.config.ib_periods
        )
        return ProfileResult(
            instrument_key=self.instrument_key,
            tpo=tpo_profile,
            day_type=day_type_result,
        )

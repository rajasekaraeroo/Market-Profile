"""Initial Balance (IB) and day-type classification.

Market Profile concepts used here:

- **Initial Balance (IB)**: the high/low range established during the first
  `ib_periods` TPO periods (default first hour — two 30-minute periods).
  It represents the market's opening "auction range."
- **Day type**: a classification of how the session developed relative to
  the IB, recomputed as more periods complete:
    - balance / non-trend: price stays inside IB most of the day.
    - normal: wide IB containing most of the day's range, little extension.
    - normal variation: one side of IB extended ~1-2x IB range.
    - trend: strong directional extension beyond IB on one side, >2x IB
      range, with little rotation back.
    - neutral: extension beyond IB on both sides.

Thresholds are expressed as multiples of the IB range and are named
constants below so they can be tuned against real session data later.
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from src.engine.tpo import TPOPeriod

# --- Tunable thresholds (multiples of IB range) ---
# Extension on a side <= this -> that side counts as "normal" (contained).
NORMAL_DAY_MAX_EXTENSION = 0.5
# Extension on a side > this -> directional, trend-day territory.
TREND_DAY_MIN_EXTENSION = 2.0


class DayType(str, Enum):
    BALANCE = "balance"
    NORMAL = "normal"
    NORMAL_VARIATION = "normal_variation"
    TREND = "trend"
    NEUTRAL = "neutral"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass
class DayTypeResult:
    day_type: DayType
    ib_high: float
    ib_low: float
    ib_range: float
    extension_up: float
    extension_down: float
    extension_up_multiple: float
    extension_down_multiple: float


def compute_initial_balance(
    df: pd.DataFrame, periods: list[TPOPeriod], ib_periods: int
) -> tuple[float, float]:
    """High/low of the first `ib_periods` TPO periods."""
    if not periods:
        raise ValueError("No periods available to compute Initial Balance")

    ib_window = periods[: min(ib_periods, len(periods))]
    ib_end = ib_window[-1].end
    ib_bars = df[df.index < ib_end]

    if ib_bars.empty:
        raise ValueError("No bars found within the Initial Balance window")

    return ib_bars["high"].max(), ib_bars["low"].min()


def classify_day_type(
    df: pd.DataFrame, periods: list[TPOPeriod], ib_periods: int
) -> DayTypeResult:
    """Classify the day type using whatever data is available so far.

    Safe to call repeatedly with progressively more periods/data during a
    live session — it always recomputes from scratch off the data passed in.
    """
    if len(periods) < ib_periods or df.empty:
        return DayTypeResult(
            day_type=DayType.INSUFFICIENT_DATA,
            ib_high=float("nan"),
            ib_low=float("nan"),
            ib_range=float("nan"),
            extension_up=float("nan"),
            extension_down=float("nan"),
            extension_up_multiple=float("nan"),
            extension_down_multiple=float("nan"),
        )

    ib_high, ib_low = compute_initial_balance(df, periods, ib_periods)
    ib_range = ib_high - ib_low

    day_high = df["high"].max()
    day_low = df["low"].min()

    extension_up = max(0.0, day_high - ib_high)
    extension_down = max(0.0, ib_low - day_low)

    if ib_range == 0:
        extension_up_multiple = float("inf") if extension_up > 0 else 0.0
        extension_down_multiple = float("inf") if extension_down > 0 else 0.0
    else:
        extension_up_multiple = extension_up / ib_range
        extension_down_multiple = extension_down / ib_range

    day_type = _classify(extension_up_multiple, extension_down_multiple)

    return DayTypeResult(
        day_type=day_type,
        ib_high=ib_high,
        ib_low=ib_low,
        ib_range=ib_range,
        extension_up=extension_up,
        extension_down=extension_down,
        extension_up_multiple=extension_up_multiple,
        extension_down_multiple=extension_down_multiple,
    )


def _classify(extension_up_multiple: float, extension_down_multiple: float) -> DayType:
    trend_up = extension_up_multiple > TREND_DAY_MIN_EXTENSION
    trend_down = extension_down_multiple > TREND_DAY_MIN_EXTENSION

    if trend_up and trend_down:
        return DayType.NEUTRAL
    if trend_up or trend_down:
        return DayType.TREND

    if (
        extension_up_multiple <= NORMAL_DAY_MAX_EXTENSION
        and extension_down_multiple <= NORMAL_DAY_MAX_EXTENSION
    ):
        return DayType.NORMAL

    extended_up = extension_up_multiple > NORMAL_DAY_MAX_EXTENSION
    extended_down = extension_down_multiple > NORMAL_DAY_MAX_EXTENSION

    if extended_up and extended_down:
        return DayType.NEUTRAL
    if extended_up or extended_down:
        return DayType.NORMAL_VARIATION
    return DayType.BALANCE

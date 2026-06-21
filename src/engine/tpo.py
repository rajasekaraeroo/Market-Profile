"""TPO (Time Price Opportunity) construction and POC/Value Area computation.

Market Profile concepts used here:

- **TPO period**: a fixed-length time slice of the session (30 minutes by
  convention). Each period is labeled with a letter (A, B, C, ...) in the
  order it occurs during the day.
- **TPO map**: for each price row (a price bucket of size `value_step`), the
  list of period letters during which price traded through that row. A
  period "touches" a row if any bar in that period's high/low range
  overlapped the row.
- **POC (Point of Control)**: the price row touched by the most periods —
  i.e. the price where the most time was spent during the session.
- **Value Area (VA)**: the band of price rows, expanding out from the POC,
  that accounts for ~70% of the session's total TPO count. This is the
  range where "most" of the day's activity happened.
"""

import string
from dataclasses import dataclass, field

import pandas as pd

from src.engine.instruments import InstrumentConfig

VALUE_AREA_PERCENT = 0.70


def _period_letter(index: int) -> str:
    """Map a 0-based period index to a TPO letter: A, B, ..., Z, AA, AB, ..."""
    letters = string.ascii_uppercase
    label = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        label = letters[remainder] + label
    return label


@dataclass
class TPOPeriod:
    letter: str
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass
class TPOProfile:
    tpo_map: dict[float, list[str]]
    poc: float
    va_high: float
    va_low: float
    total_tpo_count: int
    period_letters: list[TPOPeriod] = field(default_factory=list)


def assign_periods(
    df: pd.DataFrame, config: InstrumentConfig
) -> list[TPOPeriod]:
    """Split the session into sequential TPO periods of `tpo_period_minutes`.

    The last period absorbs whatever bars remain if the session doesn't
    divide evenly (e.g. a shortened day).
    """
    if df.empty:
        return []

    period_len = pd.Timedelta(minutes=config.tpo_period_minutes)
    session_start = df.index[0]
    session_end = df.index[-1]

    periods = []
    period_start = session_start
    index = 0
    while period_start <= session_end:
        period_end = period_start + period_len
        periods.append(
            TPOPeriod(
                letter=_period_letter(index),
                start=period_start,
                end=period_end,
            )
        )
        period_start = period_end
        index += 1
    return periods


def _bucket_rows(low: float, high: float, value_step: float) -> list[float]:
    """Return all price rows (multiples of value_step) overlapping [low, high]."""
    start_row = (low // value_step) * value_step
    rows = []
    row = start_row
    while row <= high:
        rows.append(row)
        row += value_step
    return rows


def build_tpo_map(
    df: pd.DataFrame, periods: list[TPOPeriod], value_step: float
) -> dict[float, list[str]]:
    """Build {price_row: [period letters that touched it]}."""
    tpo_map: dict[float, list[str]] = {}

    for period in periods:
        bars = df[(df.index >= period.start) & (df.index < period.end)]
        if bars.empty:
            continue
        rows_touched: set[float] = set()
        for _, bar in bars.iterrows():
            rows_touched.update(_bucket_rows(bar["low"], bar["high"], value_step))
        for row in rows_touched:
            tpo_map.setdefault(row, []).append(period.letter)

    return tpo_map


def compute_poc(tpo_map: dict[float, list[str]]) -> float:
    """Price row with the most TPO letters. Ties broken by proximity to the
    middle of the day's range (standard convention)."""
    if not tpo_map:
        raise ValueError("Cannot compute POC from an empty TPO map")

    max_count = max(len(letters) for letters in tpo_map.values())
    candidates = [row for row, letters in tpo_map.items() if len(letters) == max_count]

    if len(candidates) == 1:
        return candidates[0]

    mid = (min(tpo_map) + max(tpo_map)) / 2
    return min(candidates, key=lambda row: abs(row - mid))


def compute_value_area(
    tpo_map: dict[float, list[str]],
    poc: float,
    total_tpo_count: int,
    value_area_percent: float = VALUE_AREA_PERCENT,
) -> tuple[float, float]:
    """Expand outward from POC, two rows at a time, adding whichever single
    row (immediately above or below the current boundary) has more TPOs,
    until cumulative count reaches `value_area_percent` of the total."""
    rows_sorted = sorted(tpo_map)
    step = rows_sorted[1] - rows_sorted[0] if len(rows_sorted) > 1 else 1

    va_high = va_low = poc
    cumulative = len(tpo_map[poc])
    target = total_tpo_count * value_area_percent

    while cumulative < target:
        next_up = round(va_high + step, 10)
        next_down = round(va_low - step, 10)

        count_up = len(tpo_map.get(next_up, []))
        count_down = len(tpo_map.get(next_down, []))

        if count_up == 0 and count_down == 0:
            break

        if count_up >= count_down:
            va_high = next_up
            cumulative += count_up
        else:
            va_low = next_down
            cumulative += count_down

    return va_high, va_low


def build_tpo_profile(df: pd.DataFrame, config: InstrumentConfig) -> TPOProfile:
    """Top-level TPO construction: periods -> map -> POC -> VA."""
    periods = assign_periods(df, config)
    tpo_map = build_tpo_map(df, periods, config.value_step)

    if not tpo_map:
        return TPOProfile(
            tpo_map={},
            poc=float("nan"),
            va_high=float("nan"),
            va_low=float("nan"),
            total_tpo_count=0,
            period_letters=periods,
        )

    total_tpo_count = sum(len(letters) for letters in tpo_map.values())
    poc = compute_poc(tpo_map)
    va_high, va_low = compute_value_area(tpo_map, poc, total_tpo_count)

    return TPOProfile(
        tpo_map=tpo_map,
        poc=poc,
        va_high=va_high,
        va_low=va_low,
        total_tpo_count=total_tpo_count,
        period_letters=periods,
    )

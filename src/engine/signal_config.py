"""User-tunable thresholds for the signal engine, loaded from
config/signal_thresholds.yaml if present.

Mirrors watchlist.py's load-from-yaml-with-defaults pattern: the file is
optional, and any key it omits falls back to the built-in default. This
lets a trader dial sensitivity to their own risk style (more signals vs.
fewer, faster-confirming vs. slower) instead of being stuck with one
fixed behavior for every customer.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_SIGNAL_CONFIG_PATH = Path("config/signal_thresholds.yaml")

DEFAULT_VA_REJECTION_WINDOW_BARS = 3
DEFAULT_POC_MIGRATION_THRESHOLD_ROWS = 4
DEFAULT_DAY_TYPE_FINALIZE_AFTER_PERIODS = 8
DEFAULT_MIN_SECONDS_BETWEEN_SIGNALS = 120


@dataclass(frozen=True)
class SignalThresholds:
    va_rejection_window_bars: int = DEFAULT_VA_REJECTION_WINDOW_BARS
    poc_migration_threshold_rows: int = DEFAULT_POC_MIGRATION_THRESHOLD_ROWS
    day_type_finalize_after_periods: int = DEFAULT_DAY_TYPE_FINALIZE_AFTER_PERIODS
    min_seconds_between_signals: int = DEFAULT_MIN_SECONDS_BETWEEN_SIGNALS


def load_signal_thresholds(path: Path = DEFAULT_SIGNAL_CONFIG_PATH) -> SignalThresholds:
    if not path.exists():
        return SignalThresholds()

    raw = yaml.safe_load(path.read_text()) or {}
    return SignalThresholds(
        va_rejection_window_bars=raw.get(
            "va_rejection_window_bars", DEFAULT_VA_REJECTION_WINDOW_BARS
        ),
        poc_migration_threshold_rows=raw.get(
            "poc_migration_threshold_rows", DEFAULT_POC_MIGRATION_THRESHOLD_ROWS
        ),
        day_type_finalize_after_periods=raw.get(
            "day_type_finalize_after_periods", DEFAULT_DAY_TYPE_FINALIZE_AFTER_PERIODS
        ),
        min_seconds_between_signals=raw.get(
            "min_seconds_between_signals", DEFAULT_MIN_SECONDS_BETWEEN_SIGNALS
        ),
    )

"""Pure trigger logic: decides *when* to fire an alert, given engine/data
state. No Telegram calls here — each trigger is a small stateful class so
it can track "already alerted this session" without re-firing on every
subsequent bar, and is testable with synthetic bar sequences alone.

Call `reset()` on each trigger at the start of a new trading day.
"""

from dataclasses import dataclass

from src.engine.day_type import DayType, DayTypeResult
from src.engine.instruments import InstrumentConfig

# Bars allowed between leaving and re-entering the Value Area for it to
# still count as a "rejection" rather than just a stale excursion.
VA_REJECTION_WINDOW_BARS = 3

# POC migration threshold, expressed as a multiple of value_step so it
# scales correctly across NIFTY/BANKNIFTY/SENSEX rather than a fixed
# point count.
POC_MIGRATION_THRESHOLD_ROWS = 4

# Periods after which day-type classification is treated as settled
# enough to summarize (8 * 30min periods = 4 hours into the session).
DAY_TYPE_FINALIZE_AFTER_PERIODS = 8


@dataclass
class IBBreakoutTrigger:
    """Fires once when a bar closes beyond IB high, and once when a bar
    closes beyond IB low — never again for that same side this session."""

    alerted_up: bool = False
    alerted_down: bool = False

    def check(
        self, instrument: str, bar_close: float, day_type: DayTypeResult
    ) -> str | None:
        if day_type.day_type == DayType.INSUFFICIENT_DATA:
            return None

        if bar_close > day_type.ib_high and not self.alerted_up:
            self.alerted_up = True
            return (
                f"{instrument}: IB breakout above {day_type.ib_high:g} (IB high). "
                f"IB range was {day_type.ib_low:g}-{day_type.ib_high:g}."
            )

        if bar_close < day_type.ib_low and not self.alerted_down:
            self.alerted_down = True
            return (
                f"{instrument}: IB breakout below {day_type.ib_low:g} (IB low). "
                f"IB range was {day_type.ib_low:g}-{day_type.ib_high:g}."
            )

        return None

    def reset(self) -> None:
        self.alerted_up = False
        self.alerted_down = False


@dataclass
class VARejectionTrigger:
    """Fires once when price moves outside the Value Area and then closes
    back inside it within `VA_REJECTION_WINDOW_BARS` bars."""

    in_excursion: bool = False
    bars_outside: int = 0

    def check(
        self, instrument: str, bar_close: float, va_low: float, va_high: float
    ) -> str | None:
        outside = bar_close > va_high or bar_close < va_low

        if outside:
            if not self.in_excursion:
                self.in_excursion = True
                self.bars_outside = 0
            self.bars_outside += 1
            return None

        if self.in_excursion:
            bars_outside = self.bars_outside
            self.in_excursion = False
            self.bars_outside = 0
            if bars_outside <= VA_REJECTION_WINDOW_BARS:
                return (
                    f"{instrument}: VA rejection — price closed back inside "
                    f"Value Area ({va_low:g}-{va_high:g}) after {bars_outside} "
                    "bar(s) outside."
                )
        return None

    def reset(self) -> None:
        self.in_excursion = False
        self.bars_outside = 0


@dataclass
class POCMigrationTrigger:
    """Fires when the session's POC has shifted by more than
    `POC_MIGRATION_THRESHOLD_ROWS` * value_step from the last point this
    alerted (or from the first observed POC)."""

    last_alerted_poc: float | None = None

    def check(self, instrument: str, poc: float, config: InstrumentConfig) -> str | None:
        if self.last_alerted_poc is None:
            self.last_alerted_poc = poc
            return None

        threshold = POC_MIGRATION_THRESHOLD_ROWS * config.value_step
        if abs(poc - self.last_alerted_poc) >= threshold:
            previous = self.last_alerted_poc
            self.last_alerted_poc = poc
            return f"{instrument}: POC migration — moved from {previous:g} to {poc:g}."

        return None

    def reset(self) -> None:
        self.last_alerted_poc = None


@dataclass
class DayTypeFinalizedTrigger:
    """Fires exactly once, after enough periods have passed that the
    day-type classification is unlikely to flip again, summarizing the
    day type and IB extension stats."""

    fired: bool = False

    def check(
        self, instrument: str, period_count: int, day_type: DayTypeResult
    ) -> str | None:
        if self.fired or day_type.day_type == DayType.INSUFFICIENT_DATA:
            return None

        if period_count >= DAY_TYPE_FINALIZE_AFTER_PERIODS:
            self.fired = True
            return (
                f"{instrument}: Day type finalized — {day_type.day_type.value} "
                f"(extension up {day_type.extension_up_multiple:.1f}x IB, "
                f"down {day_type.extension_down_multiple:.1f}x IB)."
            )

        return None

    def reset(self) -> None:
        self.fired = False

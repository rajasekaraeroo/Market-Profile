"""Maps market-structure events (Session 5's triggers) onto a discretionary
options direction — "buy CE" or "buy PE" — plus a suggested strike.

Pure logic, no Telegram/UI/network here, same separation as triggers.py and
oi_analysis.py. This is read-as-structure, not a backtested edge: it tells
you which side the *shape* of the session favors, not whether the trade is
a good idea. No order placement, no position sizing — direction + context
only, for a human to act on manually in Upstox.
"""

from dataclasses import dataclass
from enum import Enum

from src.engine.day_type import DayType, DayTypeResult
from src.engine.instruments import InstrumentConfig
from src.engine.oi_analysis import OptionType, max_oi_strike

# Same window/threshold conventions as triggers.py, so the signal layer
# fires in lockstep with the alert layer.
VA_REJECTION_WINDOW_BARS = 3
POC_MIGRATION_THRESHOLD_ROWS = 4
DAY_TYPE_FINALIZE_AFTER_PERIODS = 8


class Direction(str, Enum):
    CE = "CE"  # bullish — buy a call
    PE = "PE"  # bearish — buy a put


@dataclass
class TradeSignal:
    instrument: str
    direction: Direction
    reason: str
    trigger_price: float
    suggested_strike: float | None = None

    def format(self) -> str:
        strike_part = (
            f" Suggested strike: {self.suggested_strike:g}{self.direction.value}."
            if self.suggested_strike is not None
            else ""
        )
        return (
            f"{self.instrument}: BUY {self.direction.value} — {self.reason}"
            f"{strike_part} (Signal only — not a recommendation; size and "
            f"execute at your own discretion.)"
        )


def suggest_strike(
    price: float, config: InstrumentConfig, chain: list[dict] | None, direction: Direction
) -> float | None:
    """Pick a strike near the trigger price.

    Prefers the OI-support/resistance strike from the live option chain
    (max PE OI below price for a CE buy, max CE OI above price for a PE
    buy reads as the nearest structural level); falls back to rounding the
    trigger price to the instrument's value_step if no chain snapshot is
    available yet.
    """
    if chain:
        opposite_leg: OptionType = "PE" if direction == Direction.CE else "CE"
        strike = max_oi_strike(chain, opposite_leg)
        if strike is not None:
            return strike

    step = config.value_step
    if not step:
        return None
    return round(price / step) * step


@dataclass
class IBBreakoutSignal:
    """Mirrors triggers.IBBreakoutTrigger but emits a TradeSignal with
    direction instead of a plain message — IB breakout above IB high reads
    bullish (buy CE), below IB low reads bearish (buy PE)."""

    alerted_up: bool = False
    alerted_down: bool = False

    def check(
        self,
        instrument: str,
        bar_close: float,
        day_type: DayTypeResult,
        config: InstrumentConfig,
        chain: list[dict] | None = None,
    ) -> TradeSignal | None:
        if day_type.day_type == DayType.INSUFFICIENT_DATA:
            return None

        if bar_close > day_type.ib_high and not self.alerted_up:
            self.alerted_up = True
            return TradeSignal(
                instrument=instrument,
                direction=Direction.CE,
                reason=f"IB breakout above {day_type.ib_high:g} (IB high)",
                trigger_price=bar_close,
                suggested_strike=suggest_strike(bar_close, config, chain, Direction.CE),
            )

        if bar_close < day_type.ib_low and not self.alerted_down:
            self.alerted_down = True
            return TradeSignal(
                instrument=instrument,
                direction=Direction.PE,
                reason=f"IB breakout below {day_type.ib_low:g} (IB low)",
                trigger_price=bar_close,
                suggested_strike=suggest_strike(bar_close, config, chain, Direction.PE),
            )

        return None

    def reset(self) -> None:
        self.alerted_up = False
        self.alerted_down = False


@dataclass
class VARejectionSignal:
    """Rejection at VA high (price pokes above, closes back inside) reads
    as a failed breakout — bearish, buy PE. Rejection at VA low reads
    bullish, buy CE."""

    in_excursion: bool = False
    excursion_above: bool = False
    bars_outside: int = 0

    def check(
        self,
        instrument: str,
        bar_close: float,
        va_low: float,
        va_high: float,
        config: InstrumentConfig,
        chain: list[dict] | None = None,
    ) -> TradeSignal | None:
        outside_above = bar_close > va_high
        outside_below = bar_close < va_low
        outside = outside_above or outside_below

        if outside:
            if not self.in_excursion:
                self.in_excursion = True
                self.bars_outside = 0
                self.excursion_above = outside_above
            self.bars_outside += 1
            return None

        if self.in_excursion:
            bars_outside = self.bars_outside
            was_above = self.excursion_above
            self.in_excursion = False
            self.bars_outside = 0
            if bars_outside <= VA_REJECTION_WINDOW_BARS:
                direction = Direction.PE if was_above else Direction.CE
                side = "VA high" if was_above else "VA low"
                return TradeSignal(
                    instrument=instrument,
                    direction=direction,
                    reason=f"VA rejection at {side} ({va_low:g}-{va_high:g})",
                    trigger_price=bar_close,
                    suggested_strike=suggest_strike(bar_close, config, chain, direction),
                )
        return None

    def reset(self) -> None:
        self.in_excursion = False
        self.excursion_above = False
        self.bars_outside = 0


@dataclass
class POCMigrationSignal:
    """POC sustaining a move to a new price level reads as directional
    acceptance — migrating up is bullish (buy CE), down is bearish (buy
    PE)."""

    last_alerted_poc: float | None = None

    def check(
        self,
        instrument: str,
        poc: float,
        config: InstrumentConfig,
        chain: list[dict] | None = None,
    ) -> TradeSignal | None:
        if self.last_alerted_poc is None:
            self.last_alerted_poc = poc
            return None

        threshold = POC_MIGRATION_THRESHOLD_ROWS * config.value_step
        if abs(poc - self.last_alerted_poc) >= threshold:
            previous = self.last_alerted_poc
            self.last_alerted_poc = poc
            direction = Direction.CE if poc > previous else Direction.PE
            return TradeSignal(
                instrument=instrument,
                direction=direction,
                reason=f"POC migration from {previous:g} to {poc:g}",
                trigger_price=poc,
                suggested_strike=suggest_strike(poc, config, chain, direction),
            )

        return None

    def reset(self) -> None:
        self.last_alerted_poc = None


@dataclass
class DayTypeFinalizedSignal:
    """Once day type is settled, summarize with a directional bias toward
    whichever side extended further beyond IB."""

    fired: bool = False

    def check(
        self,
        instrument: str,
        period_count: int,
        day_type: DayTypeResult,
        bar_close: float,
        config: InstrumentConfig,
        chain: list[dict] | None = None,
    ) -> TradeSignal | None:
        if self.fired or day_type.day_type == DayType.INSUFFICIENT_DATA:
            return None

        if period_count >= DAY_TYPE_FINALIZE_AFTER_PERIODS:
            self.fired = True
            direction = (
                Direction.CE
                if day_type.extension_up_multiple >= day_type.extension_down_multiple
                else Direction.PE
            )
            return TradeSignal(
                instrument=instrument,
                direction=direction,
                reason=(
                    f"Day type finalized — {day_type.day_type.value} "
                    f"(extension up {day_type.extension_up_multiple:.1f}x IB, "
                    f"down {day_type.extension_down_multiple:.1f}x IB)"
                ),
                trigger_price=bar_close,
                suggested_strike=suggest_strike(bar_close, config, chain, direction),
            )

        return None

    def reset(self) -> None:
        self.fired = False

"""Ties signals.py's structure-to-direction mapping to live engine state,
sends formatted trade signals via Telegram, and keeps a log for the UI
panel. Mirrors alert_manager.py's de-dup/rate-limit pattern — signals
reuse the same "fire once per event" triggers and the same hard
rate-limit floor, just with a CE/PE direction attached.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

from src.alerts.telegram_notifier import send_alert
from src.engine.instruments import InstrumentConfig
from src.engine.profile import ProfileResult
from src.engine.signals import (
    DayTypeFinalizedSignal,
    IBBreakoutSignal,
    POCMigrationSignal,
    TradeSignal,
    VARejectionSignal,
)

MIN_SECONDS_BETWEEN_SIGNALS = 120


@dataclass
class _InstrumentSignalTriggers:
    ib_breakout: IBBreakoutSignal = field(default_factory=IBBreakoutSignal)
    va_rejection: VARejectionSignal = field(default_factory=VARejectionSignal)
    poc_migration: POCMigrationSignal = field(default_factory=POCMigrationSignal)
    day_type_finalized: DayTypeFinalizedSignal = field(
        default_factory=DayTypeFinalizedSignal
    )

    def reset(self) -> None:
        self.ib_breakout.reset()
        self.va_rejection.reset()
        self.poc_migration.reset()
        self.day_type_finalized.reset()


class SignalManager:
    def __init__(
        self,
        notifier: Callable[[str], bool] = send_alert,
        on_signal: Callable[[TradeSignal], None] | None = None,
    ):
        self._notifier = notifier
        self._on_signal = on_signal
        self._triggers: dict[str, _InstrumentSignalTriggers] = {}
        self._last_signal_time: dict[str, dt.datetime] = {}

    def _triggers_for(self, instrument: str) -> _InstrumentSignalTriggers:
        return self._triggers.setdefault(instrument, _InstrumentSignalTriggers())

    def reset_for_new_day(self, instrument: str) -> None:
        self._triggers_for(instrument).reset()
        self._last_signal_time.pop(instrument, None)

    def _rate_limited(self, instrument: str, now: dt.datetime) -> bool:
        last = self._last_signal_time.get(instrument)
        return last is not None and (now - last).total_seconds() < MIN_SECONDS_BETWEEN_SIGNALS

    def _maybe_emit(
        self, instrument: str, signal: TradeSignal | None, now: dt.datetime
    ) -> None:
        if signal is None:
            return
        if self._rate_limited(instrument, now):
            return
        self._notifier(signal.format())
        if self._on_signal is not None:
            self._on_signal(signal)
        self._last_signal_time[instrument] = now

    def check_and_signal(
        self,
        instrument: str,
        bar_close: float,
        period_count: int,
        profile_result: ProfileResult,
        config: InstrumentConfig,
        chain: list[dict] | None = None,
        now: dt.datetime | None = None,
    ) -> None:
        """Call after each new completed bar/period, same call site as
        AlertManager.check_and_alert."""
        now = now or dt.datetime.now()
        triggers = self._triggers_for(instrument)
        day_type = profile_result.day_type

        self._maybe_emit(
            instrument,
            triggers.ib_breakout.check(instrument, bar_close, day_type, config, chain),
            now,
        )
        self._maybe_emit(
            instrument,
            triggers.va_rejection.check(
                instrument,
                bar_close,
                profile_result.va_low,
                profile_result.va_high,
                config,
                chain,
            ),
            now,
        )
        self._maybe_emit(
            instrument,
            triggers.poc_migration.check(instrument, profile_result.poc, config, chain),
            now,
        )
        self._maybe_emit(
            instrument,
            triggers.day_type_finalized.check(
                instrument, period_count, day_type, bar_close, config, chain
            ),
            now,
        )

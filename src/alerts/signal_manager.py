"""Ties signals.py's structure-to-direction mapping to live engine state,
sends formatted trade signals via Telegram, and keeps a log for the UI
panel. Mirrors alert_manager.py's de-dup/rate-limit pattern — signals
reuse the same "fire once per event" triggers and the same hard
rate-limit floor, just with a CE/PE direction attached.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

from src.alerts.signal_journal import SignalJournal
from src.alerts.telegram_notifier import send_alert
from src.engine.instruments import InstrumentConfig
from src.engine.profile import ProfileResult
from src.engine.signal_config import SignalThresholds
from src.engine.signals import (
    DayTypeFinalizedSignal,
    IBBreakoutSignal,
    POCMigrationSignal,
    TradeSignal,
    VARejectionSignal,
)


@dataclass
class _InstrumentSignalTriggers:
    thresholds: SignalThresholds = field(default_factory=SignalThresholds)
    ib_breakout: IBBreakoutSignal = field(default_factory=IBBreakoutSignal)
    va_rejection: VARejectionSignal = field(init=False)
    poc_migration: POCMigrationSignal = field(init=False)
    day_type_finalized: DayTypeFinalizedSignal = field(init=False)

    def __post_init__(self) -> None:
        self.va_rejection = VARejectionSignal(thresholds=self.thresholds)
        self.poc_migration = POCMigrationSignal(thresholds=self.thresholds)
        self.day_type_finalized = DayTypeFinalizedSignal(thresholds=self.thresholds)

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
        journal: SignalJournal | None = None,
        thresholds: SignalThresholds = SignalThresholds(),
    ):
        self._notifier = notifier
        self._on_signal = on_signal
        self._journal = journal
        self._thresholds = thresholds
        self._triggers: dict[str, _InstrumentSignalTriggers] = {}
        self._last_signal_time: dict[str, dt.datetime] = {}

    def _triggers_for(self, instrument: str) -> _InstrumentSignalTriggers:
        return self._triggers.setdefault(
            instrument, _InstrumentSignalTriggers(thresholds=self._thresholds)
        )

    def reset_for_new_day(self, instrument: str) -> None:
        self._triggers_for(instrument).reset()
        self._last_signal_time.pop(instrument, None)

    def _rate_limited(self, instrument: str, now: dt.datetime) -> bool:
        last = self._last_signal_time.get(instrument)
        return (
            last is not None
            and (now - last).total_seconds() < self._thresholds.min_seconds_between_signals
        )

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
        if self._journal is not None:
            self._journal.record(signal, now)
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
                day_type,
                config,
                chain,
            ),
            now,
        )
        self._maybe_emit(
            instrument,
            triggers.poc_migration.check(
                instrument, profile_result.poc, day_type, config, chain
            ),
            now,
        )
        self._maybe_emit(
            instrument,
            triggers.day_type_finalized.check(
                instrument, period_count, day_type, bar_close, config, chain
            ),
            now,
        )

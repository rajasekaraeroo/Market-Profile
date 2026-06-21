"""Ties trigger logic to live engine state and routes through the
Telegram notifier, with a hard rate-limit floor as a backstop against any
bug in the trigger de-duplication logic flooding the chat.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

from src.alerts.telegram_notifier import send_alert
from src.alerts.triggers import (
    DayTypeFinalizedTrigger,
    IBBreakoutTrigger,
    POCMigrationTrigger,
    VARejectionTrigger,
)
from src.engine.instruments import InstrumentConfig
from src.engine.profile import ProfileResult

# Backstop floor regardless of de-dup state: never more than one alert
# per instrument within this window.
MIN_SECONDS_BETWEEN_ALERTS = 120


@dataclass
class _InstrumentTriggers:
    ib_breakout: IBBreakoutTrigger = field(default_factory=IBBreakoutTrigger)
    va_rejection: VARejectionTrigger = field(default_factory=VARejectionTrigger)
    poc_migration: POCMigrationTrigger = field(default_factory=POCMigrationTrigger)
    day_type_finalized: DayTypeFinalizedTrigger = field(
        default_factory=DayTypeFinalizedTrigger
    )

    def reset(self) -> None:
        self.ib_breakout.reset()
        self.va_rejection.reset()
        self.poc_migration.reset()
        self.day_type_finalized.reset()


class AlertManager:
    def __init__(self, notifier: Callable[[str], bool] = send_alert):
        self._notifier = notifier
        self._triggers: dict[str, _InstrumentTriggers] = {}
        self._last_alert_time: dict[str, dt.datetime] = {}

    def _triggers_for(self, instrument: str) -> _InstrumentTriggers:
        return self._triggers.setdefault(instrument, _InstrumentTriggers())

    def reset_for_new_day(self, instrument: str) -> None:
        self._triggers_for(instrument).reset()
        self._last_alert_time.pop(instrument, None)

    def _rate_limited(self, instrument: str, now: dt.datetime) -> bool:
        last = self._last_alert_time.get(instrument)
        return last is not None and (now - last).total_seconds() < MIN_SECONDS_BETWEEN_ALERTS

    def _maybe_send(self, instrument: str, message: str | None, now: dt.datetime) -> None:
        if message is None:
            return
        if self._rate_limited(instrument, now):
            return
        self._notifier(message)
        self._last_alert_time[instrument] = now

    def check_and_alert(
        self,
        instrument: str,
        bar_close: float,
        period_count: int,
        profile_result: ProfileResult,
        config: InstrumentConfig,
        now: dt.datetime | None = None,
    ) -> None:
        """Call after each new completed bar/period."""
        now = now or dt.datetime.now()
        triggers = self._triggers_for(instrument)
        day_type = profile_result.day_type

        self._maybe_send(
            instrument, triggers.ib_breakout.check(instrument, bar_close, day_type), now
        )
        self._maybe_send(
            instrument,
            triggers.va_rejection.check(
                instrument, bar_close, profile_result.va_low, profile_result.va_high
            ),
            now,
        )
        self._maybe_send(
            instrument,
            triggers.poc_migration.check(instrument, profile_result.poc, config),
            now,
        )
        self._maybe_send(
            instrument,
            triggers.day_type_finalized.check(instrument, period_count, day_type),
            now,
        )

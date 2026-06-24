"""Bar-by-bar replay of an already-fetched historical session.

Lets a user step through how IB formed, day type settled, and signals
fired, using data that's already a single REST call away — no need to
wait for the next live session to see the tool's behavior. Mirrors
LiveFeed's bar-by-bar arrival exactly (recompute profile, then check
signals on the new bar close), just sourced from a historical DataFrame
instead of the WebSocket, so this is the same code path a real session
runs, not a separate simulation.
"""

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from src.alerts.signal_manager import SignalManager
from src.engine.instruments import InstrumentConfig
from src.engine.profile import MarketProfile, ProfileResult
from src.engine.signal_config import load_signal_thresholds
from src.engine.signals import TradeSignal


@dataclass
class ReplayStep:
    timestamp: dt.datetime
    bar_close: float
    profile_result: ProfileResult
    period_count: int
    signals: list[TradeSignal]


class ReplayEngine:
    def __init__(self, instrument: str, df: pd.DataFrame, config: InstrumentConfig):
        self.instrument = instrument
        self.df = df
        self.config = config
        self._cursor = 0
        self._collected_signals: list[TradeSignal] = []
        self._signal_manager = self._new_signal_manager()

    def _new_signal_manager(self) -> SignalManager:
        return SignalManager(
            notifier=lambda _msg: True,
            on_signal=self._collected_signals.append,
            thresholds=load_signal_thresholds(),
        )

    def __len__(self) -> int:
        return len(self.df)

    @property
    def is_finished(self) -> bool:
        return self._cursor >= len(self.df)

    def reset(self) -> None:
        self._cursor = 0
        self._collected_signals = []
        self._signal_manager = self._new_signal_manager()

    def step(self) -> ReplayStep | None:
        """Advance one bar and return the recomputed state, or None once
        the session is exhausted."""
        if self.is_finished:
            return None

        self._cursor += 1
        window = self.df.iloc[: self._cursor]
        profile_result = MarketProfile(self.instrument, window).compute()
        period_count = len(profile_result.tpo.period_letters)
        bar_close = float(window["close"].iloc[-1])
        timestamp = window.index[-1]

        self._collected_signals.clear()
        self._signal_manager.check_and_signal(
            self.instrument,
            bar_close,
            period_count,
            profile_result,
            self.config,
            now=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
        )

        return ReplayStep(
            timestamp=timestamp,
            bar_close=bar_close,
            profile_result=profile_result,
            period_count=period_count,
            signals=list(self._collected_signals),
        )

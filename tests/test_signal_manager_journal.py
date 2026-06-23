import datetime as dt

from src.alerts.signal_journal import SignalJournal
from src.alerts.signal_manager import SignalManager
from src.engine.signals import Direction, TradeSignal


def make_signal():
    return TradeSignal(
        instrument="NIFTY",
        direction=Direction.CE,
        reason="IB breakout above 25000 (IB high)",
        trigger_price=25050.0,
        suggested_strike=25000.0,
    )


def test_emitted_signal_is_written_to_journal(tmp_path):
    journal = SignalJournal(path=tmp_path / "journal.csv")
    manager = SignalManager(notifier=lambda _msg: True, journal=journal)

    manager._maybe_emit("NIFTY", make_signal(), dt.datetime(2024, 1, 2, 9, 30))

    rows = journal.read_all()
    assert len(rows) == 1
    assert rows[0]["reason"] == "IB breakout above 25000 (IB high)"


def test_rate_limited_signal_is_not_journaled(tmp_path):
    journal = SignalJournal(path=tmp_path / "journal.csv")
    manager = SignalManager(notifier=lambda _msg: True, journal=journal)

    now = dt.datetime(2024, 1, 2, 9, 30)
    manager._maybe_emit("NIFTY", make_signal(), now)
    manager._maybe_emit("NIFTY", make_signal(), now + dt.timedelta(seconds=1))

    assert len(journal.read_all()) == 1

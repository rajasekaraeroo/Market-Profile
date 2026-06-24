import datetime as dt

from src.alerts.signal_journal import SignalJournal
from src.engine.signals import Direction, TradeSignal


def make_signal(instrument="NIFTY", direction=Direction.CE, strike=25000.0):
    return TradeSignal(
        instrument=instrument,
        direction=direction,
        reason="IB breakout above 25000 (IB high)",
        trigger_price=25050.0,
        suggested_strike=strike,
    )


def test_record_then_read_all_round_trips(tmp_path):
    journal = SignalJournal(path=tmp_path / "journal.csv")
    journal.record(make_signal(), now=dt.datetime(2024, 1, 2, 9, 30))

    rows = journal.read_all()

    assert len(rows) == 1
    assert rows[0]["instrument"] == "NIFTY"
    assert rows[0]["direction"] == "CE"
    assert rows[0]["trigger_price"] == "25050.0"
    assert rows[0]["timestamp"] == "2024-01-02T09:30:00"


def test_read_all_returns_empty_list_when_file_missing(tmp_path):
    journal = SignalJournal(path=tmp_path / "missing.csv")
    assert journal.read_all() == []


def test_record_appends_across_multiple_calls(tmp_path):
    journal = SignalJournal(path=tmp_path / "journal.csv")
    journal.record(make_signal(direction=Direction.CE), now=dt.datetime(2024, 1, 2, 9, 30))
    journal.record(make_signal(direction=Direction.PE), now=dt.datetime(2024, 1, 2, 9, 35))

    rows = journal.read_all()

    assert len(rows) == 2
    assert rows[0]["direction"] == "CE"
    assert rows[1]["direction"] == "PE"

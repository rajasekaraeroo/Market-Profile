"""Persists every fired TradeSignal to a CSV file so customers have a
durable record of what the tool actually called, when, and at what price
— the "show me proof it works" ask that's the first thing a paying user
wants before trusting a signal feed.

Append-only, one row per fired signal, survives app restarts. Same flat-
file-next-to-the-app convention as upstox_auth.py's token cache, so
EXE-only users don't need a database.
"""

import csv
import datetime as dt
import os
from pathlib import Path

from src.engine.signals import TradeSignal

JOURNAL_FILE = Path(os.environ.get("SIGNAL_JOURNAL_FILE", ".signal_journal.csv"))

FIELDNAMES = [
    "timestamp",
    "instrument",
    "direction",
    "reason",
    "trigger_price",
    "suggested_strike",
]


class SignalJournal:
    def __init__(self, path: Path = JOURNAL_FILE):
        self.path = path

    def record(self, signal: TradeSignal, now: dt.datetime | None = None) -> None:
        now = now or dt.datetime.now()
        is_new = not self.path.exists()
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if is_new:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": now.isoformat(),
                    "instrument": signal.instrument,
                    "direction": signal.direction.value,
                    "reason": signal.reason,
                    "trigger_price": signal.trigger_price,
                    "suggested_strike": signal.suggested_strike,
                }
            )

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(newline="") as f:
            return list(csv.DictReader(f))

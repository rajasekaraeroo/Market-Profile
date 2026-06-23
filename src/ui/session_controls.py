"""Instrument/date/mode controls strip at the top of the main window.

This widget only collects user intent and emits signals — it has no
knowledge of the engine or data layer. `main_window.py` wires those
signals to Session 1/2 calls.
"""

import datetime as dt

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from src.data.live_feed import FEED_WINDOW_END, FEED_WINDOW_START

INSTRUMENTS = ["NIFTY", "BANKNIFTY", "SENSEX"]


def is_within_market_hours(now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now()
    return FEED_WINDOW_START <= now.time() <= FEED_WINDOW_END


class SessionControls(QWidget):
    instrument_changed = Signal(str)
    load_historical_requested = Signal(str, dt.date)
    start_live_requested = Signal(str)
    stop_live_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.instrument_combo = QComboBox()
        self.instrument_combo.addItems(INSTRUMENTS)
        self.instrument_combo.currentTextChanged.connect(
            self.instrument_changed.emit
        )

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Historical", "Live"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDate(QDate.currentDate())

        self.action_button = QPushButton("Load")
        self.action_button.clicked.connect(self._on_action_clicked)

        self.market_hours_label = QLabel("")

        layout = QHBoxLayout(self)
        layout.addWidget(QLabel("Instrument:"))
        layout.addWidget(self.instrument_combo)
        layout.addWidget(QLabel("Mode:"))
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.date_picker)
        layout.addWidget(self.action_button)
        layout.addWidget(self.market_hours_label)
        layout.addStretch()

        self._on_mode_changed(self.mode_combo.currentText())

    def _on_mode_changed(self, mode: str) -> None:
        is_live = mode == "Live"
        self.date_picker.setVisible(not is_live)

        if is_live and not is_within_market_hours():
            self.action_button.setEnabled(False)
            self.market_hours_label.setText(
                "Live mode unavailable outside market hours (09:00-15:35 IST)."
            )
        else:
            self.action_button.setEnabled(True)
            self.market_hours_label.setText("")

        self.action_button.setText("Start Live" if is_live else "Load")

    def add_instruments(self, symbols: list[str]) -> None:
        """Append watchlisted stocks to the instrument dropdown, alongside
        NIFTY/BANKNIFTY/SENSEX — they behave identically once added, no
        separate UI mode needed."""
        self.instrument_combo.addItems(symbols)

    def _on_action_clicked(self) -> None:
        instrument = self.instrument_combo.currentText()
        if self.mode_combo.currentText() == "Live":
            self.start_live_requested.emit(instrument)
        else:
            qdate = self.date_picker.date()
            date = dt.date(qdate.year(), qdate.month(), qdate.day())
            self.load_historical_requested.emit(instrument, date)

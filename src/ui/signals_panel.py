"""Live log of trade signals (direction + suggested strike), shown
alongside the profile chart and option chain so signals are visible
without needing Telegram."""

import datetime as dt

from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from src.engine.signals import Direction, TradeSignal


class SignalsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

    def add_signal(self, signal: TradeSignal) -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        self._add_row(timestamp, signal.format(), signal.direction)

    def load_history(self, rows: list[dict]) -> None:
        """Populate the panel with previously journaled signals (e.g. from
        earlier sessions/days) on startup, so the log isn't wiped by a
        restart."""
        for row in reversed(rows):
            direction = Direction(row["direction"])
            strike_part = (
                f" Suggested strike: {row['suggested_strike']}{row['direction']}."
                if row.get("suggested_strike")
                else ""
            )
            text = (
                f"{row['instrument']}: BUY {row['direction']} — {row['reason']}"
                f"{strike_part} (Signal only — not a recommendation; size and "
                f"execute at your own discretion.)"
            )
            self._add_row(row["timestamp"], text, direction)

    def _add_row(self, timestamp: str, text: str, direction: Direction) -> None:
        item = QListWidgetItem(f"[{timestamp}] {text}")
        if direction == Direction.CE:
            item.setForeground(self._color("green"))
        else:
            item.setForeground(self._color("red"))
        self.list_widget.insertItem(0, item)

    @staticmethod
    def _color(name: str):
        from PySide6.QtGui import QColor

        return QColor(name)

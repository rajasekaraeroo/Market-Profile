"""Live log of trade signals (direction + suggested strike), shown
alongside the profile chart and option chain so signals are visible
without needing Telegram."""

import datetime as dt

from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from src.engine.signals import Direction, TradeSignal


class SignalsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

    def add_signal(self, signal: TradeSignal) -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{timestamp}] {signal.format()}")
        if signal.direction == Direction.CE:
            item.setForeground(self._color("green"))
        else:
            item.setForeground(self._color("red"))
        self.list_widget.insertItem(0, item)

    @staticmethod
    def _color(name: str):
        from PyQt5.QtGui import QColor

        return QColor(name)

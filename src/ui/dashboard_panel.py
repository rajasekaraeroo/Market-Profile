"""Multi-instrument watchlist dashboard: one row per instrument (the
built-in indices plus any watchlisted stocks) summarizing live profile
state side by side, so a customer tracking several instruments doesn't
have to flip the instrument dropdown to see what each one is doing.

Pure display widget — `main_window.py` feeds it profile/signal updates,
same separation as profile_widget.py and signals_panel.py.
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from src.engine.instruments import InstrumentConfig
from src.engine.profile import ProfileResult
from src.engine.trade_quality import TradeQualityResult, score_trade_quality

COLUMNS = ["Instrument", "Last Price", "POC", "Value Area", "Initial Balance", "Day Type", "Quality", "Last Signal"]
_COL_QUALITY = 6
_COL_SIGNAL = 7


class DashboardPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)

        self._rows: dict[str, int] = {}
        self._open_poc: dict[str, float] = {}
        self._avg_ib: dict[str, float] = {}
        self._india_vix: float | None = None

    def set_india_vix(self, vix: float | None) -> None:
        self._india_vix = vix

    def set_instruments(self, instruments: list[str]) -> None:
        """(Re)initialize one blank row per tracked instrument."""
        self.table.setRowCount(len(instruments))
        self._rows = {}
        self._open_poc = {}
        self._avg_ib = {}
        for row, instrument in enumerate(instruments):
            self._rows[instrument] = row
            self.table.setItem(row, 0, QTableWidgetItem(instrument))
            for col in range(1, len(COLUMNS)):
                self.table.setItem(row, col, QTableWidgetItem(""))

    def update_row(
        self, instrument: str, bar_close: float, profile_result: ProfileResult, config: InstrumentConfig
    ) -> None:
        row = self._rows.get(instrument)
        if row is None:
            return
        day_type = profile_result.day_type

        # Record first POC as the session-open baseline for migration check.
        if instrument not in self._open_poc:
            self._open_poc[instrument] = profile_result.poc

        self._set(row, 1, f"{bar_close:g}")
        self._set(row, 2, f"{profile_result.poc:g}")
        self._set(row, 3, f"{profile_result.va_low:g}-{profile_result.va_high:g}")
        self._set(row, 4, f"{day_type.ib_low:g}-{day_type.ib_high:g}")
        self._set(row, 5, day_type.day_type.value)

        quality = score_trade_quality(
            profile_result,
            config,
            india_vix=self._india_vix,
            avg_ib_range=self._avg_ib.get(instrument),
            open_poc=self._open_poc.get(instrument),
        )
        self._set_quality(row, quality)

    def set_avg_ib_range(self, instrument: str, avg_ib: float) -> None:
        """Supply a rolling average IB range (e.g. 20-day) for better scoring."""
        self._avg_ib[instrument] = avg_ib

    def set_last_signal(self, instrument: str, text: str) -> None:
        row = self._rows.get(instrument)
        if row is None:
            return
        self._set(row, _COL_SIGNAL, text)

    def _set_quality(self, row: int, quality: TradeQualityResult) -> None:
        text = f"{quality.score}/3 {quality.label}"
        item = self.table.item(row, _COL_QUALITY)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, _COL_QUALITY, item)
        item.setText(text)
        item.setToolTip(quality.reason)
        item.setBackground(QColor(quality.colour_hint))

    def _set(self, row: int, col: int, text: str) -> None:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, col, item)
        item.setText(text)

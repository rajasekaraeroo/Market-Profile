"""Multi-instrument watchlist dashboard: one row per instrument (the
built-in indices plus any watchlisted stocks) summarizing live profile
state side by side, so a customer tracking several instruments doesn't
have to flip the instrument dropdown to see what each one is doing.

Pure display widget — `main_window.py` feeds it profile/signal updates,
same separation as profile_widget.py and signals_panel.py.
"""

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from src.engine.instruments import InstrumentConfig
from src.engine.profile import ProfileResult

COLUMNS = ["Instrument", "Last Price", "POC", "Value Area", "Initial Balance", "Day Type", "Last Signal"]


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

    def set_instruments(self, instruments: list[str]) -> None:
        """(Re)initialize one blank row per tracked instrument."""
        self.table.setRowCount(len(instruments))
        self._rows = {}
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
        self._set(row, 1, f"{bar_close:g}")
        self._set(row, 2, f"{profile_result.poc:g}")
        self._set(row, 3, f"{profile_result.va_low:g}-{profile_result.va_high:g}")
        self._set(row, 4, f"{day_type.ib_low:g}-{day_type.ib_high:g}")
        self._set(row, 5, day_type.day_type.value)

    def set_last_signal(self, instrument: str, text: str) -> None:
        row = self._rows.get(instrument)
        if row is None:
            return
        self._set(row, 6, text)

    def _set(self, row: int, col: int, text: str) -> None:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, col, item)
        item.setText(text)

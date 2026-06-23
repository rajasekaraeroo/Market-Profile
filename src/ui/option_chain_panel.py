"""Option chain table panel, displayed alongside the profile widget so
max-OI strikes can be read against the underlying's POC/VA/IB at a glance.

Only meaningful in Live mode — historical option-chain backtesting is out
of scope (Session 4 spec).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from src.engine.day_type import DayType
from src.engine.oi_analysis import OIBuildup, max_oi_strike, oi_buildup, pcr
from src.engine.profile import ProfileResult

COLUMNS = ["CE OI Chg", "CE OI", "CE LTP", "CE IV", "Strike", "PE IV", "PE LTP", "PE OI", "PE OI Chg"]

MAX_OI_TINT = QColor(255, 235, 150)
MOMENTUM_COLOR = QColor(255, 140, 0)

BUILDUP_COLORS = {
    OIBuildup.LONG_BUILDUP: QColor(180, 230, 180),
    OIBuildup.SHORT_BUILDUP: QColor(240, 170, 170),
    OIBuildup.LONG_UNWINDING: QColor(255, 220, 180),
    OIBuildup.SHORT_COVERING: QColor(190, 210, 240),
    OIBuildup.NEUTRAL: None,
}


class OptionChainPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.underlying_label = QLabel("Underlying: no data")
        self.pcr_label = QLabel("PCR: -")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)

        self.liquidity_label = QLabel("")
        self.liquidity_label.setStyleSheet("color: #a00; font-weight: bold;")
        self.liquidity_label.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.underlying_label)
        layout.addWidget(self.pcr_label)
        layout.addWidget(self.liquidity_label)
        layout.addWidget(self.table)

    def set_liquidity_flag(self, reason: str | None) -> None:
        """Show/hide the "insufficient liquidity" flag and suppress the
        option chain table when the watchlisted stock's options are too
        thin to trust (Session 6 liquidity_filter). Indices and liquid
        stocks pass `None` here and the chain renders normally."""
        is_thin = reason is not None
        self.liquidity_label.setVisible(is_thin)
        if is_thin:
            self.liquidity_label.setText(f"Insufficient liquidity for reliable OI signal: {reason}")
            self.table.setRowCount(0)
            self.pcr_label.setText("PCR: n/a (insufficient liquidity)")
        self.table.setVisible(not is_thin)

    def set_underlying_levels(self, result: ProfileResult) -> None:
        day_type = result.day_type
        ib_text = (
            f"{day_type.ib_low:g}-{day_type.ib_high:g}"
            if day_type.day_type != DayType.INSUFFICIENT_DATA
            else "n/a"
        )
        self.underlying_label.setText(
            f"Underlying — POC {result.poc:g} | VA {result.va_low:g}-{result.va_high:g} "
            f"| IB {ib_text}"
        )

    def set_chain(self, chain_now: list[dict], chain_prev: list[dict] | None = None) -> None:
        self.set_liquidity_flag(None)
        chain_prev = chain_prev or []
        self.pcr_label.setText(f"PCR: {pcr(chain_now):.2f}")

        ce_max_strike = max_oi_strike(chain_now, "CE")
        pe_max_strike = max_oi_strike(chain_now, "PE")
        buildup = oi_buildup(chain_now, chain_prev) if chain_prev else {}

        self.table.setRowCount(len(chain_now))
        for i, row in enumerate(chain_now):
            strike = row["strike"]
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            leg_buildup = buildup.get(strike, {})

            values = [
                ce.get("oi", 0) - (chain_prev_oi(chain_prev, strike, "CE")),
                ce.get("oi", 0),
                ce.get("ltp", 0.0),
                ce.get("iv", 0.0),
                strike,
                pe.get("iv", 0.0),
                pe.get("ltp", 0.0),
                pe.get("oi", 0),
                pe.get("oi", 0) - (chain_prev_oi(chain_prev, strike, "PE")),
            ]

            for col, value in enumerate(values):
                text = f"{value:g}" if isinstance(value, float) else str(value)
                column_name = COLUMNS[col]

                if column_name == "CE LTP" and ce.get("momentum"):
                    text += " \U0001F525"  # fire — fast mover, breaking out + higher highs
                elif column_name == "PE LTP" and pe.get("momentum"):
                    text += " \U0001F525"

                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)

                if column_name.startswith("CE") and strike == ce_max_strike:
                    item.setBackground(MAX_OI_TINT)
                elif column_name.startswith("PE") and strike == pe_max_strike:
                    item.setBackground(MAX_OI_TINT)

                if column_name in ("CE OI Chg",) and "CE" in leg_buildup:
                    color = BUILDUP_COLORS[leg_buildup["CE"]]
                    if color is not None:
                        item.setBackground(color)
                if column_name in ("PE OI Chg",) and "PE" in leg_buildup:
                    color = BUILDUP_COLORS[leg_buildup["PE"]]
                    if color is not None:
                        item.setBackground(color)

                # Momentum flag takes priority — it's the most actionable
                # signal in this table, so it overrides OI-buildup tinting.
                if column_name == "CE LTP" and ce.get("momentum"):
                    item.setBackground(MOMENTUM_COLOR)
                elif column_name == "PE LTP" and pe.get("momentum"):
                    item.setBackground(MOMENTUM_COLOR)

                self.table.setItem(i, col, item)

        self.table.resizeColumnsToContents()


def chain_prev_oi(chain_prev: list[dict], strike: float, option_type: str) -> float:
    for row in chain_prev:
        if row["strike"] == strike and row.get(option_type):
            return row[option_type]["oi"]
    return 0

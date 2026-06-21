"""Custom-painted TPO/Market Profile chart widget.

Renders the classic Market Profile "sideways letter histogram" — no
off-the-shelf charting library handles this shape, so we paint it directly
with QPainter. This widget does no computation of its own; it only renders
whatever `ProfileResult` (from Session 1's engine) it's given.
"""

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from src.engine.day_type import DayType
from src.engine.instruments import InstrumentConfig
from src.engine.profile import ProfileResult

HEADER_HEIGHT = 28
ROW_LABEL_WIDTH = 100
LETTERS_X_OFFSET = 8
MIN_ROW_HEIGHT = 14

VA_TINT = QColor(100, 150, 220, 60)
POC_TINT = QColor(230, 140, 30, 110)
IB_LINE_COLOR = QColor(200, 40, 40)
GRID_COLOR = QColor(210, 210, 210)

DAY_TYPE_LABELS = {
    DayType.BALANCE: "Balance",
    DayType.NORMAL: "Normal",
    DayType.NORMAL_VARIATION: "Normal Variation",
    DayType.TREND: "Trend",
    DayType.NEUTRAL: "Neutral",
    DayType.INSUFFICIENT_DATA: "Insufficient data",
}


def format_day_type_label(result: ProfileResult) -> str:
    day_type = result.day_type
    label = DAY_TYPE_LABELS.get(day_type.day_type, str(day_type.day_type))

    if day_type.day_type == DayType.INSUFFICIENT_DATA:
        return f"Day type: {label}"

    parts = [f"Day type: {label}"]
    if day_type.extension_up_multiple > 0:
        parts.append(f"extension up {day_type.extension_up_multiple:.1f}× IB")
    if day_type.extension_down_multiple > 0:
        parts.append(f"extension down {day_type.extension_down_multiple:.1f}× IB")
    return " — ".join(parts)


class ProfileWidget(QWidget):
    """Paints one instrument's TPO profile: rows of period letters, POC
    highlight, Value Area shading, and IB reference lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: ProfileResult | None = None
        self._config: InstrumentConfig | None = None
        self.setMinimumSize(420, 500)

    def set_profile(self, result: ProfileResult, config: InstrumentConfig) -> None:
        """Replace the displayed profile and repaint. Callers should only
        invoke this when a new bar/period has actually finalized (e.g. from
        Session 2's `on_bar` callback) — not on every raw tick — so the
        widget is never repainted more often than the data changes."""
        self._result = result
        self._config = config
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._result is None or not self._result.tpo.tpo_map:
            painter.drawText(self.rect(), Qt.AlignCenter, "No data loaded")
            painter.end()
            return

        self._draw_header(painter)
        self._draw_rows(painter)
        self._draw_ib_lines(painter)
        painter.end()

    def _draw_header(self, painter: QPainter) -> None:
        painter.save()
        font = QFont()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(0, 0, self.width(), HEADER_HEIGHT),
            Qt.AlignVCenter | Qt.AlignLeft,
            f"  {format_day_type_label(self._result)}",
        )
        painter.restore()

    def _chart_rows(self) -> list[float]:
        return sorted(self._result.tpo.tpo_map.keys(), reverse=True)

    def _draw_rows(self, painter: QPainter) -> None:
        rows = self._chart_rows()
        if not rows:
            return

        chart_top = HEADER_HEIGHT
        chart_height = max(self.height() - HEADER_HEIGHT, MIN_ROW_HEIGHT)
        row_height = max(chart_height / len(rows), MIN_ROW_HEIGHT)

        poc = self._result.poc
        va_high = self._result.va_high
        va_low = self._result.va_low

        font = QFont("Courier New")
        font.setPointSize(9)
        painter.setFont(font)

        for i, row in enumerate(rows):
            y = chart_top + i * row_height
            rect = QRectF(0, y, self.width(), row_height)

            if row == poc:
                painter.fillRect(rect, POC_TINT)
            elif va_low <= row <= va_high:
                painter.fillRect(rect, VA_TINT)

            painter.setPen(QPen(GRID_COLOR))
            painter.drawLine(0, int(y), self.width(), int(y))

            painter.setPen(QPen(Qt.black))
            label = f"{row:g}"
            if row == poc:
                label += " POC"
            painter.drawText(
                QRectF(4, y, ROW_LABEL_WIDTH, row_height),
                Qt.AlignVCenter | Qt.AlignLeft,
                label,
            )

            letters = "".join(self._result.tpo.tpo_map[row])
            painter.drawText(
                QRectF(
                    ROW_LABEL_WIDTH + LETTERS_X_OFFSET,
                    y,
                    self.width() - ROW_LABEL_WIDTH - LETTERS_X_OFFSET,
                    row_height,
                ),
                Qt.AlignVCenter | Qt.AlignLeft,
                letters,
            )

    def _row_to_y(self, price: float) -> float:
        rows = self._chart_rows()
        chart_top = HEADER_HEIGHT
        chart_height = max(self.height() - HEADER_HEIGHT, MIN_ROW_HEIGHT)
        row_height = max(chart_height / len(rows), MIN_ROW_HEIGHT)

        top_price = rows[0]
        step = self._config.value_step
        offset_rows = (top_price - price) / step
        return chart_top + offset_rows * row_height

    def _draw_ib_lines(self, painter: QPainter) -> None:
        day_type = self._result.day_type
        if day_type.day_type == DayType.INSUFFICIENT_DATA:
            return

        painter.save()
        pen = QPen(IB_LINE_COLOR)
        pen.setStyle(Qt.DashLine)
        pen.setWidth(2)
        painter.setPen(pen)

        for price, label in (
            (day_type.ib_high, f"IB High {day_type.ib_high:g}"),
            (day_type.ib_low, f"IB Low {day_type.ib_low:g}"),
        ):
            y = self._row_to_y(price)
            painter.drawLine(0, int(y), self.width(), int(y))
            painter.drawText(int(self.width() - 140), int(y) - 2, label)

        painter.restore()

"""Top-level application window.

Wires the UI controls to Session 1 (engine) and Session 2 (data layer)
calls. Live feed runs on a QThread so the blocking WebSocket loop never
freezes the Qt event loop — bars cross back to the UI thread via Qt's
signal/slot mechanism, which is thread-safe by design.
"""

import datetime as dt

import pandas as pd
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QVBoxLayout, QWidget

from src.data import upstox_auth
from src.data.historical import fetch_historical_session
from src.data.instrument_keys import get_instrument_key
from src.data.live_feed import Bar, LiveFeed
from src.engine.instruments import get_instrument_config
from src.engine.profile import MarketProfile
from src.ui.profile_widget import ProfileWidget
from src.ui.session_controls import SessionControls


class _NotImplementedDecoder:
    """Placeholder until Upstox's published protobuf schema for the v3
    market feed is wired in. Connecting in Live mode will surface this as
    a clear error rather than failing silently."""

    def decode(self, raw_message: bytes) -> list:
        raise NotImplementedError(
            "Live feed protobuf decoding is not implemented yet — see "
            "src/data/live_feed.py for the MarketFeedDecoder interface."
        )


class LiveFeedWorker(QThread):
    bar_received = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, live_feed: LiveFeed, parent=None):
        super().__init__(parent)
        self.live_feed = live_feed
        self.live_feed.on_bar(self.bar_received.emit)

    def run(self) -> None:
        try:
            self.live_feed.start()
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.error.emit(str(exc))

    def stop(self) -> None:
        self.live_feed.stop()
        self.wait(2000)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.controls = SessionControls()
        self.profile_widget = ProfileWidget()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.controls)
        layout.addWidget(self.profile_widget)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Ready")

        self.controls.load_historical_requested.connect(self._load_historical)
        self.controls.start_live_requested.connect(self._start_live)
        self.controls.stop_live_requested.connect(self._stop_live)

        self._live_worker: LiveFeedWorker | None = None
        self._live_bars: dict[dt.datetime, Bar] = {}
        self._live_instrument: str | None = None

        self._set_title("NIFTY", "no session loaded")

    def _set_title(self, instrument: str, suffix: str) -> None:
        self.setWindowTitle(f"Market Profile — {instrument} — {suffix}")

    def _update_status_bar(self, instrument: str, result) -> None:
        self.statusBar().showMessage(
            f"{instrument} | updated {dt.datetime.now().strftime('%H:%M:%S')} | "
            f"POC {result.poc:g} | VA {result.va_low:g}-{result.va_high:g} | "
            f"IB {result.day_type.ib_low:g}-{result.day_type.ib_high:g}"
        )

    def _load_historical(self, instrument: str, date: dt.date) -> None:
        try:
            access_token = upstox_auth.get_access_token()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Not authenticated", str(exc))
            return

        upstox_key = get_instrument_key(instrument)
        try:
            result = fetch_historical_session(upstox_key, date, access_token)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot load session", str(exc))
            return

        if result.is_partial_or_missing and result.df.empty:
            QMessageBox.information(
                self, "No data", f"No session data for {instrument} on {date} "
                "(likely a holiday)."
            )
            return

        config = get_instrument_config(instrument)
        profile_result = MarketProfile(instrument, result.df).compute()
        self.profile_widget.set_profile(profile_result, config)
        self._update_status_bar(instrument, profile_result)
        self._set_title(instrument, date.isoformat())

    def _start_live(self, instrument: str) -> None:
        try:
            access_token = upstox_auth.get_access_token()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Not authenticated", str(exc))
            return

        self._stop_live()
        self._live_bars = {}
        self._live_instrument = instrument

        upstox_key = get_instrument_key(instrument)
        live_feed = LiveFeed(
            instrument_keys=[upstox_key],
            access_token=access_token,
            decoder=_NotImplementedDecoder(),
        )

        self._live_worker = LiveFeedWorker(live_feed)
        self._live_worker.bar_received.connect(self._on_live_bar)
        self._live_worker.error.connect(self._on_live_error)
        self._live_worker.start()

        self._set_title(instrument, "LIVE")
        self.statusBar().showMessage(f"{instrument} | connecting live feed...")

    def _stop_live(self) -> None:
        if self._live_worker is not None:
            self._live_worker.stop()
            self._live_worker = None

    def _on_live_bar(self, bar: Bar) -> None:
        self._live_bars[bar.minute_start] = bar
        rows = sorted(self._live_bars.items())
        df = pd.DataFrame(
            [
                {
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                }
                for _, b in rows
            ],
            index=pd.DatetimeIndex([ts for ts, _ in rows], name="timestamp"),
        )

        config = get_instrument_config(self._live_instrument)
        profile_result = MarketProfile(self._live_instrument, df).compute()
        self.profile_widget.set_profile(profile_result, config)
        self._update_status_bar(self._live_instrument, profile_result)

    def _on_live_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Live feed error: {message}")

    def closeEvent(self, event) -> None:
        self._stop_live()
        super().closeEvent(event)

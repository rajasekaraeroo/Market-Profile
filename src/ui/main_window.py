"""Top-level application window.

Wires the UI controls to Session 1 (engine) and Session 2 (data layer)
calls. Live feed runs on a QThread so the blocking WebSocket loop never
freezes the Qt event loop — bars cross back to the UI thread via Qt's
signal/slot mechanism, which is thread-safe by design.
"""

import datetime as dt

import pandas as pd
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from src.alerts.alert_manager import AlertManager
from src.alerts.signal_manager import SignalManager
from src.data import upstox_auth
from src.data.historical import fetch_historical_session
from src.data.instrument_keys import get_instrument_key
from src.data.live_feed import Bar, LiveFeed
from src.data.instrument_keys import register_stock_instrument_key
from src.data.liquidity_filter import check_liquidity
from src.data.option_chain import OptionChainPoller, nearest_weekly_expiry
from src.data.watchlist import WatchlistError, load_watchlist
from src.engine.instruments import get_instrument_config, register_stock_instrument
from src.engine.profile import MarketProfile
from src.ui.option_chain_panel import OptionChainPanel
from src.ui.profile_widget import ProfileWidget
from src.ui.session_controls import SessionControls
from src.ui.signals_panel import SignalsPanel
from src.ui.upstox_login_dialog import UpstoxLoginDialog


class _NotImplementedDecoder:
    """Placeholder until Upstox's published protobuf schema for the v3
    market feed is wired in. Connecting in Live mode will surface this as
    a clear error rather than failing silently."""

    def decode(self, raw_message: bytes) -> list:
        raise NotImplementedError(
            "Live feed protobuf decoding is not implemented yet — see "
            "src/data/live_feed.py for the MarketFeedDecoder interface."
        )


class OptionChainBridge(QObject):
    """Bridges OptionChainPoller's background-thread callback into a Qt
    signal so the panel only ever updates on the UI thread."""

    snapshot_received = pyqtSignal(list, list)

    def make_callback(self):
        def _on_snapshot(snapshot: list[dict]) -> None:
            self.snapshot_received.emit(snapshot, self.poller.previous if self.poller else [])

        return _on_snapshot

    def __init__(self, parent=None):
        super().__init__(parent)
        self.poller: OptionChainPoller | None = None


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
        self.option_chain_panel = OptionChainPanel()
        self.signals_panel = SignalsPanel()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.profile_widget, "Profile")
        self.tabs.addTab(self.option_chain_panel, "Option Chain")
        self.tabs.addTab(self.signals_panel, "Signals")
        # Option chain and signals only make sense in Live mode.
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.controls)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Ready")

        self.controls.load_historical_requested.connect(self._load_historical)
        self.controls.start_live_requested.connect(self._start_live)
        self.controls.stop_live_requested.connect(self._stop_live)

        self._live_worker: LiveFeedWorker | None = None
        self._live_bars: dict[dt.datetime, Bar] = {}
        self._live_instrument: str | None = None
        self._period_count = 0

        self._option_chain_bridge = OptionChainBridge()
        self._option_chain_bridge.snapshot_received.connect(self._on_option_chain_snapshot)
        self._option_chain_poller: OptionChainPoller | None = None

        self._alert_manager = AlertManager()
        self._signal_manager = SignalManager(on_signal=self.signals_panel.add_signal)
        self._latest_chain_snapshot: list[dict] = []

        self._liquid_instruments: set[str] = set()
        self._load_watchlist()

        self._set_title("NIFTY", "no session loaded")

    def _load_watchlist(self) -> None:
        """Resolve config/watchlist.yaml's stocks into instruments and add
        them to the dropdown alongside NIFTY/BANKNIFTY/SENSEX (Session 6).
        A bad watchlist (oversized, or containing a non-F&O symbol) is a
        clear startup error, not a silent skip — but it must not prevent
        the indices from working, so it's caught here rather than at
        import time."""
        try:
            entries = load_watchlist()
        except WatchlistError as exc:
            QMessageBox.warning(self, "Watchlist error", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - e.g. no network for instrument master
            QMessageBox.warning(
                self, "Watchlist unavailable",
                f"Could not resolve watchlist stocks: {exc}",
            )
            return

        for entry in entries:
            register_stock_instrument(entry.symbol, entry.config.strike_interval)
            register_stock_instrument_key(entry.symbol, entry.config.instrument_key)
        if entries:
            self.controls.add_instruments([entry.symbol for entry in entries])

    def _set_title(self, instrument: str, suffix: str) -> None:
        self.setWindowTitle(f"Market Profile — {instrument} — {suffix}")

    def _update_status_bar(self, instrument: str, result) -> None:
        self.statusBar().showMessage(
            f"{instrument} | updated {dt.datetime.now().strftime('%H:%M:%S')} | "
            f"POC {result.poc:g} | VA {result.va_low:g}-{result.va_high:g} | "
            f"IB {result.day_type.ib_low:g}-{result.day_type.ib_high:g}"
        )

    def _get_access_token_or_login(self) -> str | None:
        """Return today's access token, prompting the GUI login dialog if
        none is cached yet — so an EXE-only user (no Python/terminal) can
        still complete the daily Upstox login."""
        try:
            return upstox_auth.get_access_token()
        except RuntimeError:
            dialog = UpstoxLoginDialog(self)
            if dialog.exec_() != UpstoxLoginDialog.Accepted:
                return None
        try:
            return upstox_auth.get_access_token()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Not authenticated", str(exc))
            return None

    def _load_historical(self, instrument: str, date: dt.date) -> None:
        access_token = self._get_access_token_or_login()
        if access_token is None:
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
        access_token = self._get_access_token_or_login()
        if access_token is None:
            return

        self._stop_live()
        self._live_bars = {}
        self._live_instrument = instrument
        self._period_count = 0
        self._alert_manager.reset_for_new_day(instrument)
        self._signal_manager.reset_for_new_day(instrument)
        self._latest_chain_snapshot = []

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

        self._option_chain_bridge.poller = OptionChainPoller(
            instrument_key=upstox_key,
            expiry_date=nearest_weekly_expiry(),
            access_token=access_token,
            on_snapshot=self._option_chain_bridge.make_callback(),
        )
        self._option_chain_poller = self._option_chain_bridge.poller
        self._option_chain_poller.start()
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, True)

        self._set_title(instrument, "LIVE")
        self.statusBar().showMessage(f"{instrument} | connecting live feed...")

    def _stop_live(self) -> None:
        if self._live_worker is not None:
            self._live_worker.stop()
            self._live_worker = None
        if self._option_chain_poller is not None:
            self._option_chain_poller.stop()
            self._option_chain_poller = None
            self._option_chain_bridge.poller = None
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)

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
        self.option_chain_panel.set_underlying_levels(profile_result)
        self._update_status_bar(self._live_instrument, profile_result)

        self._period_count = len(profile_result.tpo.period_letters)
        self._alert_manager.check_and_alert(
            self._live_instrument, bar.close, self._period_count, profile_result, config
        )
        self._signal_manager.check_and_signal(
            self._live_instrument,
            bar.close,
            self._period_count,
            profile_result,
            config,
            chain=self._latest_chain_snapshot,
        )

    def _on_option_chain_snapshot(self, snapshot: list, previous: list) -> None:
        self._latest_chain_snapshot = snapshot
        liquidity = check_liquidity(snapshot)
        if not liquidity.is_liquid:
            self.option_chain_panel.set_liquidity_flag(liquidity.reason)
            return
        self.option_chain_panel.set_chain(snapshot, previous)

    def _on_live_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Live feed error: {message}")

    def closeEvent(self, event) -> None:
        self._stop_live()
        super().closeEvent(event)

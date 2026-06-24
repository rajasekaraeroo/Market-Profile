"""Live tick feed: aggregates Upstox WebSocket LTP ticks into rolling
1-minute OHLC bars and feeds them to the engine incrementally.

Index instruments (NIFTY, BANKNIFTY, SENSEX) stream last-traded-price
(LTP) ticks, not pre-built candles, so this module builds 1-minute bars
itself: open = first tick in the minute, high/low = running max/min,
close = most recent tick, and the bar finalizes when the minute boundary
passes.

Protobuf decoding (`UpstoxProtobufDecoder`) uses the compiled
`MarketDataFeedV3_pb2` schema shipped inside the `upstox-python-sdk`
package (already a `requirements.txt` dependency) rather than a
hand-rolled `.proto` — that schema is generated and maintained by
Upstox themselves, so it tracks their published v3 feed format directly.
"""

import datetime as dt
import json
import logging
import ssl
import time as time_module
import uuid
from dataclasses import dataclass
from typing import Callable, Protocol

import websocket

from src.data.historical import fetch_historical_session

logger = logging.getLogger(__name__)

MARKET_FEED_URL = "wss://api.upstox.com/v3/feed/market-data-feed"

# Index instruments only ever need last-traded-price — "ltpc" is the
# lightest subscription mode Upstox offers and is sufficient for building
# 1-minute bars from ticks.
FEED_MODE = "ltpc"

# Small buffer either side of actual 09:15-15:30 market hours.
FEED_WINDOW_START = dt.time(9, 0)
FEED_WINDOW_END = dt.time(15, 35)

RECONNECT_BACKOFF_SECONDS = (2, 4, 8, 16, 30)


@dataclass(frozen=True)
class Tick:
    instrument_key: str
    timestamp: dt.datetime
    ltp: float


@dataclass
class Bar:
    instrument_key: str
    minute_start: dt.datetime
    open: float
    high: float
    low: float
    close: float

    def update(self, ltp: float) -> None:
        self.high = max(self.high, ltp)
        self.low = min(self.low, ltp)
        self.close = ltp


class MarketFeedDecoder(Protocol):
    """Turns one raw WebSocket message into zero or more ticks."""

    def decode(self, raw_message: bytes) -> list[Tick]: ...


class UpstoxProtobufDecoder:
    """Decodes Upstox v3 `FeedResponse` protobuf messages into ticks,
    using the compiled schema from `upstox_client.feeder.proto` (the
    SDK package Upstox publishes and maintains) rather than a vendored
    `.proto` file we'd have to keep in sync ourselves.

    Only handles the "ltpc" feed mode — the lightest mode and the only
    one index instruments need (Session 2 spec: LTP ticks, not OHLC).
    """

    def __init__(self):
        from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as feed_pb2

        self._feed_pb2 = feed_pb2

    def _extract_ltpc(self, feed):
        if feed.HasField("ltpc"):
            return feed.ltpc
        if feed.HasField("fullFeed"):
            full = feed.fullFeed
            if full.HasField("marketFF") and full.marketFF.HasField("ltpc"):
                return full.marketFF.ltpc
            if full.HasField("indexFF") and full.indexFF.HasField("ltpc"):
                return full.indexFF.ltpc
        return None

    def decode(self, raw_message: bytes) -> list[Tick]:
        response = self._feed_pb2.FeedResponse()
        response.ParseFromString(raw_message)

        ticks = []
        for instrument_key, feed in response.feeds.items():
            ltpc = self._extract_ltpc(feed)
            if ltpc is None or ltpc.ltp == 0:
                continue

            timestamp = (
                dt.datetime.fromtimestamp(ltpc.ltt / 1000)
                if ltpc.ltt
                else dt.datetime.now()
            )
            ticks.append(
                Tick(instrument_key=instrument_key, timestamp=timestamp, ltp=ltpc.ltp)
            )
        return ticks


def build_subscribe_message(instrument_keys: list[str], mode: str = FEED_MODE) -> bytes:
    """Upstox's v3 feed subscription handshake: a JSON request sent as a
    binary WebSocket frame right after the connection opens."""
    request = {
        "guid": str(uuid.uuid4()),
        "method": "sub",
        "data": {"instrumentKeys": instrument_keys, "mode": mode},
    }
    return json.dumps(request).encode("utf-8")


def _minute_start(timestamp: dt.datetime) -> dt.datetime:
    return timestamp.replace(second=0, microsecond=0)


class BarAggregator:
    """Aggregates a stream of ticks (possibly for multiple instruments)
    into finalized 1-minute bars.

    Call `on_tick` for every incoming tick; it returns the bar that just
    finalized if the tick crossed a minute boundary, else None. Call
    `flush` to force-finalize any open bars (e.g. at session end).
    """

    def __init__(self):
        self._open_bars: dict[str, Bar] = {}

    def on_tick(self, tick: Tick) -> Bar | None:
        minute_start = _minute_start(tick.timestamp)
        current = self._open_bars.get(tick.instrument_key)
        finalized = None

        if current is None:
            self._open_bars[tick.instrument_key] = Bar(
                instrument_key=tick.instrument_key,
                minute_start=minute_start,
                open=tick.ltp,
                high=tick.ltp,
                low=tick.ltp,
                close=tick.ltp,
            )
            return None

        if minute_start > current.minute_start:
            finalized = current
            self._open_bars[tick.instrument_key] = Bar(
                instrument_key=tick.instrument_key,
                minute_start=minute_start,
                open=tick.ltp,
                high=tick.ltp,
                low=tick.ltp,
                close=tick.ltp,
            )
        else:
            current.update(tick.ltp)

        return finalized

    def flush(self, instrument_key: str) -> Bar | None:
        return self._open_bars.pop(instrument_key, None)


def _within_feed_window(now: dt.datetime) -> bool:
    return FEED_WINDOW_START <= now.time() <= FEED_WINDOW_END


class LiveFeed:
    """Manages the WebSocket connection, tick aggregation, reconnection
    with gap backfill, and callback dispatch for one or more instruments.
    """

    def __init__(
        self,
        instrument_keys: list[str],
        access_token: str,
        decoder: MarketFeedDecoder,
    ):
        self.instrument_keys = instrument_keys
        self.access_token = access_token
        self.decoder = decoder
        self.aggregator = BarAggregator()
        self._last_bar_end: dict[str, dt.datetime] = {}
        self._bar_callbacks: list[Callable[[Bar], None]] = []
        self._tick_callbacks: list[Callable[[Tick], None]] = []
        self._running = False
        self._ws: websocket.WebSocketApp | None = None

    def on_bar(self, callback: Callable[[Bar], None]) -> None:
        self._bar_callbacks.append(callback)

    def on_tick(self, callback: Callable[[Tick], None]) -> None:
        self._tick_callbacks.append(callback)

    def _emit_bar(self, bar: Bar) -> None:
        self._last_bar_end[bar.instrument_key] = bar.minute_start + dt.timedelta(
            minutes=1
        )
        for callback in self._bar_callbacks:
            callback(bar)

    def _handle_message(self, raw_message: bytes) -> None:
        for tick in self.decoder.decode(raw_message):
            for callback in self._tick_callbacks:
                callback(tick)
            finalized = self.aggregator.on_tick(tick)
            if finalized is not None:
                self._emit_bar(finalized)

    def _backfill_gap(self, instrument_key: str, gap_start: dt.datetime) -> None:
        """If a reconnect leaves a hole in the minute series, pull the
        missed minutes from the historical API rather than leaving a gap
        in the profile."""
        logger.warning(
            "Backfilling gap for %s starting %s", instrument_key, gap_start
        )
        result = fetch_historical_session(
            instrument_key, gap_start.date(), self.access_token
        )
        if result.is_partial_or_missing:
            logger.warning("No backfill data available for %s", gap_start.date())
            return
        for row_timestamp, row in result.df[result.df.index >= gap_start].iterrows():
            bar = Bar(
                instrument_key=instrument_key,
                minute_start=row_timestamp,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
            )
            self._emit_bar(bar)

    def start(self) -> None:
        """Connect and run until market close or `stop()` is called.
        Reconnects automatically on disconnect, backfilling any gap."""
        self._running = True
        attempt = 0

        while self._running:
            now = dt.datetime.now()
            if not _within_feed_window(now):
                logger.info("Outside feed window (%s) — not connecting.", now.time())
                break

            try:
                self._connect_and_run()
                attempt = 0
            except Exception:
                logger.exception("Live feed connection dropped")

            if not self._running:
                break

            backoff = RECONNECT_BACKOFF_SECONDS[
                min(attempt, len(RECONNECT_BACKOFF_SECONDS) - 1)
            ]
            attempt += 1
            time_module.sleep(backoff)

            for instrument_key, gap_start in list(self._last_bar_end.items()):
                self._backfill_gap(instrument_key, gap_start)

    def _subscribe(self, ws) -> None:
        ws.send(
            build_subscribe_message(self.instrument_keys),
            opcode=websocket.ABNF.OPCODE_BINARY,
        )

    def _connect_and_run(self) -> None:
        self._ws = websocket.WebSocketApp(
            MARKET_FEED_URL,
            header={"Authorization": f"Bearer {self.access_token}"},
            on_open=lambda ws: self._subscribe(ws),
            on_message=lambda ws, message: self._handle_message(message),
        )
        # Matches the official SDK's websocket-client sslopt — Upstox's
        # market-feed WebSocket cert chain isn't fully verifiable through
        # certifi's default bundle, so the SDK itself disables hostname
        # verification rather than failing every connection.
        self._ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def stop(self) -> None:
        """Flush any open bars and shut down cleanly."""
        self._running = False
        for instrument_key in self.instrument_keys:
            bar = self.aggregator.flush(instrument_key)
            if bar is not None:
                self._emit_bar(bar)
        if self._ws is not None:
            self._ws.close()

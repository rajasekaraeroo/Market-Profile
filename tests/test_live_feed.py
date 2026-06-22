import datetime as dt
import json

import pandas as pd
import pytest

from src.data.historical import HistoricalSessionResult
from src.data.live_feed import (
    Bar,
    BarAggregator,
    LiveFeed,
    Tick,
    UpstoxProtobufDecoder,
    build_subscribe_message,
)


def make_tick(minute: int, second: int, ltp: float, key="NIFTY") -> Tick:
    return Tick(
        instrument_key=key,
        timestamp=dt.datetime(2024, 1, 2, 9, minute, second),
        ltp=ltp,
    )


def test_aggregator_builds_ohlc_within_one_minute():
    aggregator = BarAggregator()

    assert aggregator.on_tick(make_tick(15, 0, 100.0)) is None
    assert aggregator.on_tick(make_tick(15, 10, 105.0)) is None
    assert aggregator.on_tick(make_tick(15, 20, 95.0)) is None
    assert aggregator.on_tick(make_tick(15, 59, 102.0)) is None

    # Crossing into the next minute finalizes the previous bar.
    finalized = aggregator.on_tick(make_tick(16, 0, 103.0))

    assert finalized.open == 100.0
    assert finalized.high == 105.0
    assert finalized.low == 95.0
    assert finalized.close == 102.0
    assert finalized.minute_start == dt.datetime(2024, 1, 2, 9, 15)


def test_aggregator_flush_returns_open_bar():
    aggregator = BarAggregator()
    aggregator.on_tick(make_tick(15, 0, 100.0))

    bar = aggregator.flush("NIFTY")

    assert bar is not None
    assert bar.close == 100.0
    assert aggregator.flush("NIFTY") is None


def test_aggregator_tracks_multiple_instruments_independently():
    aggregator = BarAggregator()
    aggregator.on_tick(make_tick(15, 0, 100.0, key="NIFTY"))
    aggregator.on_tick(make_tick(15, 0, 50000.0, key="BANKNIFTY"))

    nifty_bar = aggregator.flush("NIFTY")
    banknifty_bar = aggregator.flush("BANKNIFTY")

    assert nifty_bar.close == 100.0
    assert banknifty_bar.close == 50000.0


class StubDecoder:
    def decode(self, raw_message):
        return []


def test_live_feed_backfills_gap_on_reconnect(monkeypatch):
    feed = LiveFeed(["NIFTY"], access_token="fake-token", decoder=StubDecoder())

    received_bars: list[Bar] = []
    feed.on_bar(received_bars.append)

    # Simulate a normal bar arriving, then a dropped connection that
    # leaves a one-minute gap before the next tick.
    aggregator_bar = Bar(
        instrument_key="NIFTY",
        minute_start=dt.datetime(2024, 1, 2, 9, 15),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )
    feed._emit_bar(aggregator_bar)

    gap_df = pd.DataFrame(
        {
            "open": [100.5],
            "high": [101.0],
            "low": [100.0],
            "close": [100.8],
        },
        index=pd.DatetimeIndex([dt.datetime(2024, 1, 2, 9, 16)], name="timestamp"),
    )

    def fake_fetch(instrument_key, date, access_token):
        return HistoricalSessionResult(df=gap_df, is_partial_or_missing=False)

    monkeypatch.setattr("src.data.live_feed.fetch_historical_session", fake_fetch)

    feed._backfill_gap("NIFTY", dt.datetime(2024, 1, 2, 9, 16))

    assert len(received_bars) == 2
    assert received_bars[-1].minute_start == dt.datetime(2024, 1, 2, 9, 16)
    assert received_bars[-1].close == 100.8


def test_build_subscribe_message_shape():
    raw = build_subscribe_message(["NSE_INDEX|Nifty 50"])
    payload = json.loads(raw.decode("utf-8"))

    assert payload["method"] == "sub"
    assert payload["data"]["instrumentKeys"] == ["NSE_INDEX|Nifty 50"]
    assert payload["data"]["mode"] == "ltpc"
    assert "guid" in payload


pytest.importorskip("upstox_client", reason="upstox-python-sdk not installed")


def test_protobuf_decoder_decodes_ltpc_feed():
    from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as feed_pb2

    response = feed_pb2.FeedResponse()
    response.type = feed_pb2.Type.live_feed
    feed = response.feeds["NSE_INDEX|Nifty 50"]
    feed.ltpc.ltp = 25012.5
    feed.ltpc.ltt = 1700000000000  # epoch millis

    decoder = UpstoxProtobufDecoder()
    ticks = decoder.decode(response.SerializeToString())

    assert len(ticks) == 1
    assert ticks[0].instrument_key == "NSE_INDEX|Nifty 50"
    assert ticks[0].ltp == 25012.5
    assert ticks[0].timestamp == dt.datetime.fromtimestamp(1700000000000 / 1000)


def test_protobuf_decoder_skips_feeds_without_ltp():
    from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as feed_pb2

    response = feed_pb2.FeedResponse()
    response.feeds["NSE_INDEX|Nifty 50"]  # touch the map entry, leave it empty

    decoder = UpstoxProtobufDecoder()
    assert decoder.decode(response.SerializeToString()) == []


def test_protobuf_decoder_reads_full_feed_index_mode():
    from upstox_client.feeder.proto import MarketDataFeedV3_pb2 as feed_pb2

    response = feed_pb2.FeedResponse()
    feed = response.feeds["NSE_INDEX|Nifty Bank"]
    feed.fullFeed.indexFF.ltpc.ltp = 51000.0
    feed.fullFeed.indexFF.ltpc.ltt = 1700000000000

    decoder = UpstoxProtobufDecoder()
    ticks = decoder.decode(response.SerializeToString())

    assert len(ticks) == 1
    assert ticks[0].ltp == 51000.0

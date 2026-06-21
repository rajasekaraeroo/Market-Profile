import pytest

from src.data.watchlist import WatchlistError, load_watchlist


def make_entries():
    return [
        {
            "segment": "NSE_FO",
            "name": "RELIANCE",
            "trading_symbol": "RELIANCE",
            "instrument_key": "NSE_FO|RELIANCE",
            "lot_size": 250,
            "strike_interval": 20.0,
        },
        {
            "segment": "NSE_FO",
            "name": "TCS",
            "trading_symbol": "TCS",
            "instrument_key": "NSE_FO|TCS",
            "lot_size": 150,
            "strike_interval": 50.0,
        },
    ]


def write_watchlist(tmp_path, symbols):
    path = tmp_path / "watchlist.yaml"
    body = "stocks:\n" + "".join(f"  - {s}\n" for s in symbols)
    path.write_text(body)
    return path


def test_load_watchlist_resolves_valid_symbols(tmp_path):
    path = write_watchlist(tmp_path, ["RELIANCE", "TCS"])
    entries = load_watchlist(path=path, entries=make_entries())
    assert {e.symbol for e in entries} == {"RELIANCE", "TCS"}
    assert all(e.config.fno_eligible for e in entries)


def test_load_watchlist_missing_file_returns_empty(tmp_path):
    path = tmp_path / "missing.yaml"
    assert load_watchlist(path=path, entries=make_entries()) == []


def test_load_watchlist_rejects_non_fno_symbol(tmp_path):
    path = write_watchlist(tmp_path, ["RELIANCE", "ZOMATO"])
    with pytest.raises(WatchlistError, match="ZOMATO"):
        load_watchlist(path=path, entries=make_entries())


def test_load_watchlist_rejects_oversized_list(tmp_path):
    path = write_watchlist(tmp_path, ["RELIANCE", "TCS"])
    with pytest.raises(WatchlistError, match="exceeding"):
        load_watchlist(path=path, max_size=1, entries=make_entries())

import pytest

from src.data.instrument_master import get_stock_config, is_fno_eligible


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
        {
            "segment": "NSE_EQ",
            "name": "ZOMATO",
            "trading_symbol": "ZOMATO",
            "instrument_key": "NSE_EQ|ZOMATO",
            "lot_size": 1,
            "strike_interval": 0,
        },
    ]


def test_get_stock_config_resolves_known_symbol():
    entries = make_entries()
    config = get_stock_config("RELIANCE", entries=entries)
    assert config.instrument_key == "NSE_FO|RELIANCE"
    assert config.lot_size == 250
    assert config.strike_interval == 20.0
    assert config.fno_eligible is True


def test_get_stock_config_is_case_insensitive():
    entries = make_entries()
    config = get_stock_config("tcs", entries=entries)
    assert config.symbol == "TCS"


def test_get_stock_config_rejects_non_fno_symbol():
    entries = make_entries()
    with pytest.raises(ValueError, match="not F&O-eligible"):
        get_stock_config("ZOMATO", entries=entries)


def test_get_stock_config_rejects_unknown_symbol():
    entries = make_entries()
    with pytest.raises(ValueError, match="not F&O-eligible"):
        get_stock_config("NOPE", entries=entries)


def test_is_fno_eligible():
    entries = make_entries()
    assert is_fno_eligible("RELIANCE", entries=entries) is True
    assert is_fno_eligible("ZOMATO", entries=entries) is False

import pandas as pd

from src.engine.instruments import get_instrument_config, register_stock_instrument
from src.engine.profile import MarketProfile


def test_register_stock_instrument_uses_strike_interval_as_value_step():
    config = register_stock_instrument("RELIANCE", strike_interval=20.0)
    assert config.value_step == 20.0
    assert get_instrument_config("RELIANCE") is config


def test_registered_stock_does_not_disturb_index_configs():
    register_stock_instrument("TCS", strike_interval=50.0)
    nifty = get_instrument_config("NIFTY")
    assert nifty.value_step == 25


def test_profile_engine_works_unmodified_for_a_registered_stock():
    register_stock_instrument("HDFCBANK", strike_interval=20.0)
    index = pd.date_range("2024-01-02 09:15", "2024-01-02 10:15", freq="1min")
    df = pd.DataFrame(
        {
            "open": 1500.0,
            "high": 1505.0,
            "low": 1495.0,
            "close": 1500.0,
        },
        index=index,
    )
    result = MarketProfile("HDFCBANK", df).compute()
    assert result.instrument_key == "HDFCBANK"
    assert result.poc is not None

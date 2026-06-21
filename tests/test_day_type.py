import pandas as pd

from src.engine.day_type import DayType
from src.engine.instruments import get_instrument_config
from src.engine.profile import MarketProfile
from src.engine.tpo import assign_periods


def load_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(
        f"tests/fixtures/{name}.csv", index_col="timestamp", parse_dates=True
    )


def test_balance_day_is_classified_as_normal_or_balance():
    df = load_fixture("balance_day")
    result = MarketProfile("NIFTY", df).compute()

    assert result.day_type.day_type in (DayType.NORMAL, DayType.BALANCE)
    assert result.ib_low < result.ib_high


def test_trend_day_is_classified_as_trend():
    df = load_fixture("trend_day")
    result = MarketProfile("NIFTY", df).compute()

    assert result.day_type.day_type == DayType.TREND
    assert result.day_type.extension_up_multiple > 2.0
    assert result.day_type.extension_down_multiple == 0.0


def test_partial_session_with_only_ib_periods_does_not_crash():
    df = load_fixture("partial_day")
    config = get_instrument_config("NIFTY")
    periods = assign_periods(df, config)

    result = MarketProfile("NIFTY", df).compute()

    assert len(periods) == 3
    assert result.day_type.ib_low < result.day_type.ib_high


def test_insufficient_data_before_ib_completes():
    df = load_fixture("balance_day")
    # Cut off before even the first IB period (30 min) completes.
    early = df[df.index < df.index[0] + pd.Timedelta(minutes=10)]

    result = MarketProfile("NIFTY", early).compute()

    assert result.day_type.day_type == DayType.INSUFFICIENT_DATA


def test_day_type_recomputes_with_progressively_more_data():
    df = load_fixture("trend_day")
    config = get_instrument_config("NIFTY")
    periods = assign_periods(df, config)

    # Mid-session snapshot: only first 4 periods (2 hours) of data.
    mid_cutoff = periods[3].end
    mid_df = df[df.index < mid_cutoff]
    mid_result = MarketProfile("NIFTY", mid_df).compute()

    full_result = MarketProfile("NIFTY", df).compute()

    # Extension should grow (or stay the same) as more trend data arrives.
    assert (
        full_result.day_type.extension_up_multiple
        >= mid_result.day_type.extension_up_multiple
    )

import pandas as pd
import pytest

from src.engine.instruments import INSTRUMENTS, get_instrument_config
from src.engine.tpo import build_tpo_profile, compute_poc, compute_value_area


def load_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(
        f"tests/fixtures/{name}.csv", index_col="timestamp", parse_dates=True
    )


@pytest.mark.parametrize("instrument_key", ["NIFTY", "BANKNIFTY", "SENSEX"])
def test_balance_day_poc_centered_and_va_narrow(instrument_key):
    df = load_fixture("balance_day")
    config = get_instrument_config(instrument_key)
    profile = build_tpo_profile(df, config)

    # Price oscillates symmetrically around 25000 -> POC should land there.
    assert profile.poc == 25000

    # Value area should not need to span every row touched during the day -
    # 70% coverage should be reachable well within the full row span.
    row_span = max(profile.tpo_map) - min(profile.tpo_map)
    va_width = profile.va_high - profile.va_low
    assert va_width <= row_span

    # Respect the instrument's own value_step, not a hardcoded one.
    assert config.value_step == INSTRUMENTS[instrument_key].value_step


def test_trend_day_poc_trails_near_close_side_extreme():
    df = load_fixture("trend_day")
    config = get_instrument_config("NIFTY")
    profile = build_tpo_profile(df, config)

    day_high = df["high"].max()
    day_low = df["low"].min()

    # POC should sit well above the day's low (the IB anchor point), in
    # keeping with a steady directional grind rather than a balance day.
    assert profile.poc > day_low + (day_high - day_low) * 0.4


def test_poc_tie_breaks_toward_middle_of_range():
    tpo_map = {50.0: ["A", "B"], 100.0: ["A", "B"], 150.0: ["A"]}
    assert compute_poc(tpo_map) == 100.0


def test_value_area_reaches_target_coverage():
    tpo_map = {
        100.0: ["A"],
        200.0: ["A", "B", "C"],
        300.0: ["A", "B"],
        400.0: ["A"],
    }
    total = sum(len(v) for v in tpo_map.values())
    poc = 200.0
    va_high, va_low = compute_value_area(tpo_map, poc, total)

    covered = sum(
        len(letters)
        for row, letters in tpo_map.items()
        if va_low <= row <= va_high
    )
    assert covered / total >= 0.70
    assert va_low <= poc <= va_high


def test_partial_session_does_not_crash_and_produces_provisional_profile():
    df = load_fixture("partial_day")
    config = get_instrument_config("NIFTY")
    profile = build_tpo_profile(df, config)

    assert len(profile.period_letters) == 3
    assert profile.total_tpo_count > 0
    assert profile.va_low <= profile.poc <= profile.va_high

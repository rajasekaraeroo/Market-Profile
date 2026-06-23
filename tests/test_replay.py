import pandas as pd

from src.engine.instruments import get_instrument_config
from src.engine.replay import ReplayEngine


def load_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(
        f"tests/fixtures/{name}.csv", index_col="timestamp", parse_dates=True
    )


def test_replay_steps_through_every_bar_and_reports_finished():
    df = load_fixture("trend_day")
    config = get_instrument_config("NIFTY")
    engine = ReplayEngine("NIFTY", df, config)

    steps = 0
    while not engine.is_finished:
        step = engine.step()
        assert step is not None
        steps += 1

    assert steps == len(df)
    assert engine.step() is None


def test_replay_fires_ib_breakout_signal_on_trend_day():
    df = load_fixture("trend_day")
    config = get_instrument_config("NIFTY")
    engine = ReplayEngine("NIFTY", df, config)

    all_signals = []
    while not engine.is_finished:
        step = engine.step()
        all_signals.extend(step.signals)

    assert any(s.reason.startswith("IB breakout above") for s in all_signals)


def test_replay_reset_clears_progress_and_signal_state():
    df = load_fixture("trend_day")
    config = get_instrument_config("NIFTY")
    engine = ReplayEngine("NIFTY", df, config)

    for _ in range(10):
        engine.step()
    assert not engine.is_finished

    engine.reset()

    assert engine._cursor == 0
    first_step = engine.step()
    assert first_step.timestamp == df.index[0]


def test_replay_step_returns_growing_profile_state():
    df = load_fixture("trend_day")
    config = get_instrument_config("NIFTY")
    engine = ReplayEngine("NIFTY", df, config)

    first = engine.step()
    assert first.period_count >= 1
    assert first.bar_close == df["close"].iloc[0]

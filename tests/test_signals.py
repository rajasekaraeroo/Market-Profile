from src.engine.day_type import DayType, DayTypeResult
from src.engine.instruments import get_instrument_config
from src.engine.signal_config import SignalThresholds
from src.engine.signals import (
    DayTypeFinalizedSignal,
    Direction,
    IBBreakoutSignal,
    POCMigrationSignal,
    VARejectionSignal,
    suggest_strike,
    suggest_stop_loss,
)


def make_day_type(ib_low=24900, ib_high=25000, day_type=DayType.NORMAL, up=1.5, down=0.0):
    return DayTypeResult(
        day_type=day_type,
        ib_high=ib_high,
        ib_low=ib_low,
        ib_range=ib_high - ib_low,
        extension_up=0.0,
        extension_down=0.0,
        extension_up_multiple=up,
        extension_down_multiple=down,
    )


def test_ib_breakout_above_signals_ce():
    trigger = IBBreakoutSignal()
    config = get_instrument_config("NIFTY")
    signal = trigger.check("NIFTY", 25050, make_day_type(), config)
    assert signal is not None
    assert signal.direction == Direction.CE
    # Must not re-fire while still above IB high.
    assert trigger.check("NIFTY", 25060, make_day_type(), config) is None


def test_ib_breakout_below_signals_pe():
    trigger = IBBreakoutSignal()
    config = get_instrument_config("NIFTY")
    signal = trigger.check("NIFTY", 24800, make_day_type(), config)
    assert signal is not None
    assert signal.direction == Direction.PE


def test_va_rejection_at_high_signals_pe():
    trigger = VARejectionSignal()
    config = get_instrument_config("NIFTY")
    day_type = make_day_type()
    assert trigger.check("NIFTY", 25150, 24900, 25100, day_type, config) is None
    signal = trigger.check("NIFTY", 25050, 24900, 25100, day_type, config)
    assert signal is not None
    assert signal.direction == Direction.PE


def test_va_rejection_at_low_signals_ce():
    trigger = VARejectionSignal()
    config = get_instrument_config("NIFTY")
    day_type = make_day_type()
    assert trigger.check("NIFTY", 24850, 24900, 25100, day_type, config) is None
    signal = trigger.check("NIFTY", 24950, 24900, 25100, day_type, config)
    assert signal is not None
    assert signal.direction == Direction.CE


def test_va_rejection_respects_custom_window_threshold():
    thresholds = SignalThresholds(va_rejection_window_bars=1)
    trigger = VARejectionSignal(thresholds=thresholds)
    config = get_instrument_config("NIFTY")
    day_type = make_day_type()
    # Two bars outside exceeds the tightened 1-bar window, so no signal.
    assert trigger.check("NIFTY", 25150, 24900, 25100, day_type, config) is None
    assert trigger.check("NIFTY", 25160, 24900, 25100, day_type, config) is None
    assert trigger.check("NIFTY", 25050, 24900, 25100, day_type, config) is None


def test_poc_migration_up_signals_ce():
    trigger = POCMigrationSignal()
    config = get_instrument_config("NIFTY")
    day_type = make_day_type()
    trigger.check("NIFTY", 25000, day_type, config)
    threshold = trigger.thresholds.poc_migration_threshold_rows * config.value_step
    signal = trigger.check("NIFTY", 25000 + threshold, day_type, config)
    assert signal is not None
    assert signal.direction == Direction.CE


def test_poc_migration_down_signals_pe():
    trigger = POCMigrationSignal()
    config = get_instrument_config("NIFTY")
    day_type = make_day_type()
    trigger.check("NIFTY", 25000, day_type, config)
    threshold = trigger.thresholds.poc_migration_threshold_rows * config.value_step
    signal = trigger.check("NIFTY", 25000 - threshold, day_type, config)
    assert signal is not None
    assert signal.direction == Direction.PE


def test_suggest_stop_loss_ce_uses_ib_low():
    day_type = make_day_type(ib_low=24900, ib_high=25000)
    assert suggest_stop_loss(Direction.CE, day_type) == 24900


def test_suggest_stop_loss_pe_uses_ib_high():
    day_type = make_day_type(ib_low=24900, ib_high=25000)
    assert suggest_stop_loss(Direction.PE, day_type) == 25000


def test_suggest_stop_loss_none_when_insufficient_data():
    day_type = make_day_type(day_type=DayType.INSUFFICIENT_DATA)
    assert suggest_stop_loss(Direction.CE, day_type) is None


def test_day_type_finalized_bullish_extension_signals_ce():
    trigger = DayTypeFinalizedSignal()
    config = get_instrument_config("NIFTY")
    day_type = make_day_type(up=2.0, down=0.5)
    signal = trigger.check("NIFTY", 8, day_type, 25050, config)
    assert signal is not None
    assert signal.direction == Direction.CE
    # Fires only once.
    assert trigger.check("NIFTY", 9, day_type, 25050, config) is None


def test_day_type_finalized_bearish_extension_signals_pe():
    trigger = DayTypeFinalizedSignal()
    config = get_instrument_config("NIFTY")
    day_type = make_day_type(up=0.5, down=2.0)
    signal = trigger.check("NIFTY", 8, day_type, 24950, config)
    assert signal is not None
    assert signal.direction == Direction.PE


def test_suggest_strike_falls_back_to_value_step_rounding_without_chain():
    config = get_instrument_config("NIFTY")
    strike = suggest_strike(25012, config, None, Direction.CE)
    assert strike == 25000


def test_suggest_strike_uses_chain_max_oi_when_available():
    config = get_instrument_config("NIFTY")
    chain = [
        {"strike": 24900, "CE": {"oi": 100}, "PE": {"oi": 9000}},
        {"strike": 25100, "CE": {"oi": 50}, "PE": {"oi": 200}},
    ]
    # Buying CE -> look at PE OI (support) -> max PE OI strike is 24900.
    strike = suggest_strike(25000, config, chain, Direction.CE)
    assert strike == 24900

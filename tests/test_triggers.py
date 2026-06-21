from src.engine.day_type import DayType, DayTypeResult
from src.engine.instruments import get_instrument_config
from src.alerts.triggers import (
    DAY_TYPE_FINALIZE_AFTER_PERIODS,
    POC_MIGRATION_THRESHOLD_ROWS,
    VA_REJECTION_WINDOW_BARS,
    DayTypeFinalizedTrigger,
    IBBreakoutTrigger,
    POCMigrationTrigger,
    VARejectionTrigger,
)


def make_day_type(ib_low=24900, ib_high=25000, day_type=DayType.NORMAL):
    return DayTypeResult(
        day_type=day_type,
        ib_high=ib_high,
        ib_low=ib_low,
        ib_range=ib_high - ib_low,
        extension_up=0.0,
        extension_down=0.0,
        extension_up_multiple=1.5,
        extension_down_multiple=0.0,
    )


def test_ib_breakout_fires_once_per_side():
    trigger = IBBreakoutTrigger()
    day_type = make_day_type()

    assert trigger.check("NIFTY", 25050, day_type) is not None
    # Still above IB high on the next bar — must not re-fire.
    assert trigger.check("NIFTY", 25060, day_type) is None

    # Breakout on the other side still fires independently.
    assert trigger.check("NIFTY", 24800, day_type) is not None
    assert trigger.check("NIFTY", 24700, day_type) is None


def test_ib_breakout_does_nothing_with_insufficient_data():
    trigger = IBBreakoutTrigger()
    day_type = make_day_type(day_type=DayType.INSUFFICIENT_DATA)
    assert trigger.check("NIFTY", 30000, day_type) is None


def test_ib_breakout_reset_allows_refire():
    trigger = IBBreakoutTrigger()
    day_type = make_day_type()
    trigger.check("NIFTY", 25050, day_type)
    trigger.reset()
    assert trigger.check("NIFTY", 25060, day_type) is not None


def test_va_rejection_fires_once_when_back_inside_within_window():
    trigger = VARejectionTrigger()

    assert trigger.check("NIFTY", 25150, 24900, 25100) is None  # leaves VA
    assert trigger.check("NIFTY", 25050, 24900, 25100) is not None  # back inside


def test_va_rejection_does_not_fire_if_still_outside():
    trigger = VARejectionTrigger()
    assert trigger.check("NIFTY", 25150, 24900, 25100) is None
    assert trigger.check("NIFTY", 25160, 24900, 25100) is None


def test_va_rejection_does_not_fire_if_excursion_too_long():
    trigger = VARejectionTrigger()
    trigger.check("NIFTY", 25150, 24900, 25100)
    for _ in range(VA_REJECTION_WINDOW_BARS):
        trigger.check("NIFTY", 25150, 24900, 25100)
    # Now back inside, but it took too many bars to qualify as a rejection.
    assert trigger.check("NIFTY", 25050, 24900, 25100) is None


def test_va_rejection_fires_again_on_a_new_excursion():
    trigger = VARejectionTrigger()
    trigger.check("NIFTY", 25150, 24900, 25100)
    first = trigger.check("NIFTY", 25050, 24900, 25100)
    assert first is not None

    trigger.check("NIFTY", 25150, 24900, 25100)
    second = trigger.check("NIFTY", 25050, 24900, 25100)
    assert second is not None


def test_poc_migration_does_not_fire_on_first_observation():
    trigger = POCMigrationTrigger()
    config = get_instrument_config("NIFTY")
    assert trigger.check("NIFTY", 25000, config) is None


def test_poc_migration_fires_when_shift_exceeds_threshold():
    trigger = POCMigrationTrigger()
    config = get_instrument_config("NIFTY")
    trigger.check("NIFTY", 25000, config)

    threshold = POC_MIGRATION_THRESHOLD_ROWS * config.value_step
    just_under = 25000 + threshold - config.value_step
    assert trigger.check("NIFTY", just_under, config) is None

    just_over = 25000 + threshold
    assert trigger.check("NIFTY", just_over, config) is not None


def test_poc_migration_does_not_refire_for_same_level():
    trigger = POCMigrationTrigger()
    config = get_instrument_config("NIFTY")
    trigger.check("NIFTY", 25000, config)
    threshold = POC_MIGRATION_THRESHOLD_ROWS * config.value_step
    trigger.check("NIFTY", 25000 + threshold, config)
    # No further movement -> no re-fire.
    assert trigger.check("NIFTY", 25000 + threshold, config) is None


def test_day_type_finalized_fires_once_after_threshold_periods():
    trigger = DayTypeFinalizedTrigger()
    day_type = make_day_type()

    for period_count in range(DAY_TYPE_FINALIZE_AFTER_PERIODS):
        assert trigger.check("NIFTY", period_count, day_type) is None

    assert (
        trigger.check("NIFTY", DAY_TYPE_FINALIZE_AFTER_PERIODS, day_type) is not None
    )
    # Doesn't fire again on subsequent periods.
    assert (
        trigger.check("NIFTY", DAY_TYPE_FINALIZE_AFTER_PERIODS + 1, day_type) is None
    )


def test_day_type_finalized_skips_insufficient_data():
    trigger = DayTypeFinalizedTrigger()
    day_type = make_day_type(day_type=DayType.INSUFFICIENT_DATA)
    assert (
        trigger.check("NIFTY", DAY_TYPE_FINALIZE_AFTER_PERIODS + 5, day_type) is None
    )

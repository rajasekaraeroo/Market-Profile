import datetime as dt

from src.alerts.alert_manager import MIN_SECONDS_BETWEEN_ALERTS, AlertManager
from src.engine.day_type import DayType, DayTypeResult
from src.engine.instruments import get_instrument_config
from src.engine.profile import ProfileResult
from src.engine.tpo import TPOProfile


def make_profile_result(poc=25050, va_low=24950, va_high=25100, ib_low=24900, ib_high=25000):
    tpo = TPOProfile(
        tpo_map={poc: ["A"]},
        poc=poc,
        va_high=va_high,
        va_low=va_low,
        total_tpo_count=1,
        period_letters=[],
    )
    day_type = DayTypeResult(
        day_type=DayType.NORMAL,
        ib_high=ib_high,
        ib_low=ib_low,
        ib_range=ib_high - ib_low,
        extension_up=0.0,
        extension_down=0.0,
        extension_up_multiple=0.5,
        extension_down_multiple=0.0,
    )
    return ProfileResult(instrument_key="NIFTY", tpo=tpo, day_type=day_type)


def test_check_and_alert_sends_ib_breakout_via_notifier():
    sent = []
    manager = AlertManager(notifier=sent.append)
    config = get_instrument_config("NIFTY")
    result = make_profile_result()

    now = dt.datetime(2024, 1, 2, 9, 30)
    manager.check_and_alert("NIFTY", bar_close=25050, period_count=1, profile_result=result, config=config, now=now)

    assert len(sent) == 1
    assert "IB breakout" in sent[0]


def test_rate_limit_blocks_second_alert_within_window():
    sent = []
    manager = AlertManager(notifier=sent.append)
    config = get_instrument_config("NIFTY")

    now = dt.datetime(2024, 1, 2, 9, 30)
    # IB breakout fires immediately and consumes the alert slot.
    result = make_profile_result(va_low=24950, va_high=25100)
    manager.check_and_alert("NIFTY", 25050, 1, result, config, now=now)
    assert len(sent) == 1

    # A genuinely new VA-rejection excursion starts and resolves moments
    # later — still inside the rate-limit window, so it must be dropped.
    soon_after = now + dt.timedelta(seconds=10)
    manager.check_and_alert("NIFTY", 25150, 2, result, config, now=soon_after)  # leaves VA
    manager.check_and_alert("NIFTY", 25050, 3, result, config, now=soon_after)  # back inside
    assert len(sent) == 1

    # After the window elapses, a fresh excursion is allowed through.
    later = now + dt.timedelta(seconds=MIN_SECONDS_BETWEEN_ALERTS + 1)
    manager.check_and_alert("NIFTY", 25150, 4, result, config, now=later)  # leaves VA
    manager.check_and_alert("NIFTY", 25050, 5, result, config, now=later)  # back inside
    assert len(sent) == 2


def test_reset_for_new_day_clears_trigger_state_and_rate_limit():
    sent = []
    manager = AlertManager(notifier=sent.append)
    config = get_instrument_config("NIFTY")
    result = make_profile_result()

    now = dt.datetime(2024, 1, 2, 9, 30)
    manager.check_and_alert("NIFTY", 25050, 1, result, config, now=now)
    assert len(sent) == 1

    manager.reset_for_new_day("NIFTY")

    # Same instant timestamp would normally be rate-limited, but a new day
    # should clear both trigger de-dup state and the rate-limit clock.
    manager.check_and_alert("NIFTY", 25050, 1, result, config, now=now)
    assert len(sent) == 2


def test_different_instruments_are_independent():
    sent = []
    manager = AlertManager(notifier=sent.append)
    config = get_instrument_config("NIFTY")
    result = make_profile_result()

    now = dt.datetime(2024, 1, 2, 9, 30)
    manager.check_and_alert("NIFTY", 25050, 1, result, config, now=now)
    manager.check_and_alert("BANKNIFTY", 25050, 1, result, config, now=now)

    assert len(sent) == 2

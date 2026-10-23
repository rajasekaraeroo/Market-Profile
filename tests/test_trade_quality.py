from src.engine.day_type import DayType, DayTypeResult
from src.engine.instruments import get_instrument_config
from src.engine.profile import ProfileResult
from src.engine.tpo import TPOProfile
from src.engine.trade_quality import TradeQualityCheck, score_trade_quality


def _make_profile(poc=25000, va_low=24950, va_high=25050, ib_low=24900, ib_high=25100):
    tpo = TPOProfile(
        tpo_map={},
        poc=poc,
        va_high=va_high,
        va_low=va_low,
        total_tpo_count=0,
    )
    day_type = DayTypeResult(
        day_type=DayType.NORMAL,
        ib_high=ib_high,
        ib_low=ib_low,
        ib_range=ib_high - ib_low,
        extension_up=0.0,
        extension_down=0.0,
        extension_up_multiple=1.0,
        extension_down_multiple=0.0,
    )
    return ProfileResult(instrument_key="NSE_INDEX|Nifty 50", tpo=tpo, day_type=day_type)


def test_all_checks_pass_score_3():
    profile = _make_profile()
    config = get_instrument_config("NIFTY")
    result = score_trade_quality(
        profile, config,
        india_vix=15.0,
        avg_ib_range=150.0,   # IB=200 > 35% of 150
        open_poc=24900.0,     # migration = 2 rows at step=50
    )
    assert result.score == 3
    assert result.label == "High"
    assert result.checks[TradeQualityCheck.VIX_OK] is True
    assert result.checks[TradeQualityCheck.IB_WIDE] is True
    assert result.checks[TradeQualityCheck.POC_MIGRATED] is True


def test_low_vix_fails_vix_check():
    profile = _make_profile()
    config = get_instrument_config("NIFTY")
    result = score_trade_quality(profile, config, india_vix=9.5)
    assert result.checks[TradeQualityCheck.VIX_OK] is False
    assert result.score <= 2


def test_narrow_ib_fails_ib_check():
    profile = _make_profile(ib_low=24990, ib_high=25010)   # IB = 20
    config = get_instrument_config("NIFTY")
    result = score_trade_quality(
        profile, config,
        india_vix=15.0,
        avg_ib_range=200.0,   # 20 < 35% of 200 = 70
    )
    assert result.checks[TradeQualityCheck.IB_WIDE] is False


def test_no_poc_migration_fails_poc_check():
    profile = _make_profile(poc=25000)
    config = get_instrument_config("NIFTY")
    result = score_trade_quality(
        profile, config,
        india_vix=15.0,
        open_poc=25000.0,   # no movement
    )
    assert result.checks[TradeQualityCheck.POC_MIGRATED] is False


def test_skip_label_when_score_below_2():
    profile = _make_profile(ib_low=24990, ib_high=25010, poc=25000)
    config = get_instrument_config("NIFTY")
    result = score_trade_quality(
        profile, config,
        india_vix=8.0,        # fail VIX
        avg_ib_range=300.0,   # fail IB
        open_poc=25000.0,     # fail POC migration
    )
    assert result.score == 0
    assert result.label == "Skip"


def test_no_vix_supplied_does_not_penalise():
    profile = _make_profile()
    config = get_instrument_config("NIFTY")
    result = score_trade_quality(profile, config, india_vix=None)
    # VIX check absent; IB and POC both default to OK → score 2
    assert TradeQualityCheck.VIX_OK not in result.checks
    assert result.score == 2

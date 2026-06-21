from src.engine.oi_analysis import OIBuildup, max_oi_strike, oi_buildup, pcr


def make_chain():
    return [
        {"strike": 24900, "CE": {"ltp": 150.0, "oi": 1000}, "PE": {"ltp": 60.0, "oi": 4000}},
        {"strike": 25000, "CE": {"ltp": 100.0, "oi": 5000}, "PE": {"ltp": 90.0, "oi": 3000}},
        {"strike": 25100, "CE": {"ltp": 60.0, "oi": 3000}, "PE": {"ltp": 140.0, "oi": 6000}},
    ]


def test_max_oi_strike_per_option_type():
    chain = make_chain()
    assert max_oi_strike(chain, "CE") == 25000
    assert max_oi_strike(chain, "PE") == 25100


def test_max_oi_strike_empty_chain_returns_none():
    assert max_oi_strike([], "CE") is None


def test_pcr_is_total_pe_oi_over_total_ce_oi():
    chain = make_chain()
    total_pe = 4000 + 3000 + 6000
    total_ce = 1000 + 5000 + 3000
    assert pcr(chain) == total_pe / total_ce


def test_pcr_zero_ce_oi_with_pe_oi_is_infinite():
    chain = [{"strike": 100, "CE": {"ltp": 1.0, "oi": 0}, "PE": {"ltp": 1.0, "oi": 500}}]
    assert pcr(chain) == float("inf")


def test_pcr_zero_oi_both_sides_is_zero():
    chain = [{"strike": 100, "CE": {"ltp": 1.0, "oi": 0}, "PE": {"ltp": 1.0, "oi": 0}}]
    assert pcr(chain) == 0.0


def test_oi_buildup_long_buildup_price_up_oi_up():
    prev = [{"strike": 25000, "CE": {"ltp": 100.0, "oi": 1000}, "PE": None}]
    now = [{"strike": 25000, "CE": {"ltp": 110.0, "oi": 1500}, "PE": None}]
    result = oi_buildup(now, prev)
    assert result[25000]["CE"] == OIBuildup.LONG_BUILDUP


def test_oi_buildup_short_buildup_price_down_oi_up():
    prev = [{"strike": 25000, "CE": {"ltp": 100.0, "oi": 1000}, "PE": None}]
    now = [{"strike": 25000, "CE": {"ltp": 90.0, "oi": 1500}, "PE": None}]
    result = oi_buildup(now, prev)
    assert result[25000]["CE"] == OIBuildup.SHORT_BUILDUP


def test_oi_buildup_long_unwinding_price_down_oi_down():
    prev = [{"strike": 25000, "CE": {"ltp": 100.0, "oi": 1500}, "PE": None}]
    now = [{"strike": 25000, "CE": {"ltp": 90.0, "oi": 1000}, "PE": None}]
    result = oi_buildup(now, prev)
    assert result[25000]["CE"] == OIBuildup.LONG_UNWINDING


def test_oi_buildup_short_covering_price_up_oi_down():
    prev = [{"strike": 25000, "CE": {"ltp": 100.0, "oi": 1500}, "PE": None}]
    now = [{"strike": 25000, "CE": {"ltp": 110.0, "oi": 1000}, "PE": None}]
    result = oi_buildup(now, prev)
    assert result[25000]["CE"] == OIBuildup.SHORT_COVERING


def test_oi_buildup_skips_strikes_not_present_in_previous_snapshot():
    prev = [{"strike": 25000, "CE": {"ltp": 100.0, "oi": 1000}, "PE": None}]
    now = [
        {"strike": 25000, "CE": {"ltp": 110.0, "oi": 1500}, "PE": None},
        {"strike": 25100, "CE": {"ltp": 50.0, "oi": 200}, "PE": None},
    ]
    result = oi_buildup(now, prev)
    assert 25100 not in result

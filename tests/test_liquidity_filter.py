from src.data.liquidity_filter import (
    MIN_STRIKES_WITH_OI,
    MIN_TOTAL_OI,
    check_liquidity,
)


def make_liquid_chain():
    chain = []
    for i in range(MIN_STRIKES_WITH_OI + 2):
        strike = 100 + i * 10
        chain.append(
            {
                "strike": strike,
                "CE": {"ltp": 10.0, "oi": MIN_TOTAL_OI // MIN_STRIKES_WITH_OI},
                "PE": {"ltp": 8.0, "oi": MIN_TOTAL_OI // MIN_STRIKES_WITH_OI},
            }
        )
    return chain


def make_thin_chain():
    return [
        {"strike": 100, "CE": {"ltp": 1.0, "oi": 50}, "PE": {"ltp": 1.0, "oi": 30}},
        {"strike": 110, "CE": {"ltp": 1.0, "oi": 0}, "PE": {"ltp": 1.0, "oi": 0}},
    ]


def test_liquid_chain_passes():
    result = check_liquidity(make_liquid_chain())
    assert result.is_liquid is True
    assert result.reason is None


def test_thin_chain_fails_total_oi():
    result = check_liquidity(make_thin_chain())
    assert result.is_liquid is False
    assert "total OI" in result.reason


def test_thin_chain_fails_strikes_with_oi():
    chain = [
        {
            "strike": 100,
            "CE": {"ltp": 1.0, "oi": MIN_TOTAL_OI},
            "PE": {"ltp": 1.0, "oi": MIN_TOTAL_OI},
        }
    ]
    result = check_liquidity(chain)
    assert result.is_liquid is False
    assert "strikes with OI" in result.reason


def test_empty_chain_is_not_liquid():
    result = check_liquidity([])
    assert result.is_liquid is False
    assert result.total_oi == 0
    assert result.strikes_with_oi == 0

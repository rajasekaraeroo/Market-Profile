"""Liquidity gate for watchlisted stocks' option chains.

Index option chains (NIFTY/BANKNIFTY/SENSEX) are always liquid enough to
trust. Individual F&O stocks vary wildly — some watchlisted stock might
have deep, liquid options; another might have a thin chain where OI-based
signals (PCR, buildup classification, max-OI strike) would be noise
dressed up as a signal. This module decides, per stock, whether to trust
the option-chain-derived parts of the UI/alerts for it.

The underlying's own price profile (TPO/POC/Value Area/IB) is always
shown regardless of this check — that's just equity price data and is
meaningful no matter how thin the options are.
"""

from dataclasses import dataclass

# Tunable thresholds, not hardcoded inline, so they can be adjusted
# without hunting through the check logic.
MIN_TOTAL_OI = 50_000
MIN_STRIKES_WITH_OI = 5


@dataclass(frozen=True)
class LiquidityResult:
    is_liquid: bool
    total_oi: int
    strikes_with_oi: int
    reason: str | None = None


def _leg_oi(leg: dict | None) -> int:
    if not leg:
        return 0
    return int(leg.get("oi", 0))


def check_liquidity(chain: list[dict]) -> LiquidityResult:
    """Classify an option chain snapshot (Session 4's chain shape:
    `[{"strike":, "CE": {...} | None, "PE": {...} | None}, ...]`) as
    liquid enough for OI-derived signals, or not.

    A strike "has OI" if either its CE or PE leg has non-zero OI.
    """
    total_oi = 0
    strikes_with_oi = 0

    for row in chain:
        ce_oi = _leg_oi(row.get("CE"))
        pe_oi = _leg_oi(row.get("PE"))
        total_oi += ce_oi + pe_oi
        if ce_oi > 0 or pe_oi > 0:
            strikes_with_oi += 1

    if total_oi < MIN_TOTAL_OI:
        return LiquidityResult(
            is_liquid=False,
            total_oi=total_oi,
            strikes_with_oi=strikes_with_oi,
            reason=f"total OI {total_oi} below minimum {MIN_TOTAL_OI}",
        )

    if strikes_with_oi < MIN_STRIKES_WITH_OI:
        return LiquidityResult(
            is_liquid=False,
            total_oi=total_oi,
            strikes_with_oi=strikes_with_oi,
            reason=(
                f"only {strikes_with_oi} strikes with OI, "
                f"below minimum {MIN_STRIKES_WITH_OI}"
            ),
        )

    return LiquidityResult(
        is_liquid=True, total_oi=total_oi, strikes_with_oi=strikes_with_oi
    )

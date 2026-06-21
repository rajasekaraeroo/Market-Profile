"""Pure-logic helpers for reading an option chain snapshot: max-OI strikes,
put-call ratio, and OI buildup classification.

No network/UI dependencies — same pattern as Session 1's engine, operating
on plain dicts so it's independently testable with synthetic chain data.

**Chain snapshot shape** (what `option_chain.py` is expected to produce):

    [
        {
            "strike": 25000,
            "CE": {"ltp": 120.5, "oi": 50000, "volume": 1200, "iv": 14.2},
            "PE": {"ltp": 95.0, "oi": 42000, "volume": 900, "iv": 13.8},
        },
        ...
    ]

OI buildup needs two consecutive snapshots (current vs previous poll) to
read both the OI change and the price change direction for each leg.
"""

from enum import Enum

OptionType = str  # "CE" or "PE"


class OIBuildup(str, Enum):
    LONG_BUILDUP = "long_buildup"  # price up, OI up
    SHORT_BUILDUP = "short_buildup"  # price down, OI up
    LONG_UNWINDING = "long_unwinding"  # price down, OI down
    SHORT_COVERING = "short_covering"  # price up, OI down
    NEUTRAL = "neutral"  # no meaningful change in either


def max_oi_strike(chain: list[dict], option_type: OptionType) -> float | None:
    """Strike with the highest OI for CE or PE — commonly read as a
    support (max PE OI) / resistance (max CE OI) proxy."""
    rows = [row for row in chain if row.get(option_type)]
    if not rows:
        return None
    return max(rows, key=lambda row: row[option_type]["oi"])["strike"]


def pcr(chain: list[dict]) -> float:
    """Put-call ratio: total PE OI / total CE OI."""
    total_pe_oi = sum(row["PE"]["oi"] for row in chain if row.get("PE"))
    total_ce_oi = sum(row["CE"]["oi"] for row in chain if row.get("CE"))
    if total_ce_oi == 0:
        return float("inf") if total_pe_oi > 0 else 0.0
    return total_pe_oi / total_ce_oi


def _classify_leg(price_change: float, oi_change: float) -> OIBuildup:
    if oi_change > 0 and price_change > 0:
        return OIBuildup.LONG_BUILDUP
    if oi_change > 0 and price_change < 0:
        return OIBuildup.SHORT_BUILDUP
    if oi_change < 0 and price_change < 0:
        return OIBuildup.LONG_UNWINDING
    if oi_change < 0 and price_change > 0:
        return OIBuildup.SHORT_COVERING
    return OIBuildup.NEUTRAL


def oi_buildup(
    chain_now: list[dict], chain_prev: list[dict]
) -> dict[float, dict[OptionType, OIBuildup]]:
    """Classify each strike's CE and PE leg into one of the four standard
    OI buildup buckets by comparing the current snapshot to the previous
    poll."""
    prev_by_strike = {row["strike"]: row for row in chain_prev}
    result: dict[float, dict[OptionType, OIBuildup]] = {}

    for row in chain_now:
        strike = row["strike"]
        prev_row = prev_by_strike.get(strike)
        if prev_row is None:
            continue

        legs: dict[OptionType, OIBuildup] = {}
        for option_type in ("CE", "PE"):
            now_leg = row.get(option_type)
            prev_leg = prev_row.get(option_type)
            if not now_leg or not prev_leg:
                continue
            price_change = now_leg["ltp"] - prev_leg["ltp"]
            oi_change = now_leg["oi"] - prev_leg["oi"]
            legs[option_type] = _classify_leg(price_change, oi_change)

        if legs:
            result[strike] = legs

    return result

"""Trade quality scoring — answers "is today a day worth trading?"

Synthesises three independent checks into a 0–3 score:

  +1  India VIX is in a tradeable range (above floor, below panic ceiling)
  +1  Initial Balance is meaningfully wide vs. recent history
  +1  POC has migrated enough to signal directional participation

Score 3 → high-quality, trade normally.
Score 2 → marginal, trade smaller / tighter stops.
Score 0–1 → skip or paper-trade only (choppy / flat-VIX / narrow day).

All three checks are computed from data already available in `ProfileResult`
and `InstrumentConfig`; no extra feed is required.  The VIX check requires
the caller to supply the current India VIX reading (fetched separately); pass
`None` to skip it (score cap becomes 2).
"""

from dataclasses import dataclass
from enum import Enum

from src.engine.instruments import InstrumentConfig
from src.engine.profile import ProfileResult

# --- Tunable thresholds ---
VIX_FLOOR = 11.0        # Below this: premium too thin, edge vanishes
VIX_CEILING = 35.0      # Above this: gap risk and wide spreads dominate
IB_WIDTH_RATIO = 0.35   # IB must be > this fraction of 20-day avg IB
POC_MIGRATION_MIN = 2   # POC must move at least this many rows from open


class TradeQualityCheck(str, Enum):
    VIX_OK = "vix_ok"
    IB_WIDE = "ib_wide"
    POC_MIGRATED = "poc_migrated"


@dataclass
class TradeQualityResult:
    score: int                          # 0–3
    checks: dict[TradeQualityCheck, bool]
    label: str                          # "High" / "Marginal" / "Skip"
    reason: str                         # human-readable explanation

    @property
    def colour_hint(self) -> str:
        """Qt stylesheet colour for the score cell."""
        if self.score == 3:
            return "#2e7d32"   # green
        if self.score == 2:
            return "#f57c00"   # amber
        return "#c62828"       # red


def score_trade_quality(
    profile: ProfileResult,
    config: InstrumentConfig,
    *,
    india_vix: float | None = None,
    avg_ib_range: float | None = None,
    open_poc: float | None = None,
) -> TradeQualityResult:
    """Compute a trade-quality score from the current profile state.

    Parameters
    ----------
    profile:
        The latest `ProfileResult` for the instrument.
    config:
        Instrument config (provides `value_step` for POC row counting).
    india_vix:
        Current India VIX level.  Pass ``None`` to skip the VIX check.
    avg_ib_range:
        Rolling average IB range (e.g. 20-day).  Pass ``None`` to skip the
        IB-width check (it will count as passed to avoid false negatives when
        history isn't available yet).
    open_poc:
        POC at the session open (first bar).  Pass ``None`` to skip the
        POC-migration check.
    """
    checks: dict[TradeQualityCheck, bool] = {}

    # --- Check 1: India VIX ---
    if india_vix is not None:
        vix_ok = VIX_FLOOR <= india_vix <= VIX_CEILING
        checks[TradeQualityCheck.VIX_OK] = vix_ok
    # If not supplied, we don't penalise.

    # --- Check 2: IB width ---
    ib_range = profile.day_type.ib_range
    if avg_ib_range and avg_ib_range > 0:
        ib_wide = ib_range >= IB_WIDTH_RATIO * avg_ib_range
    else:
        ib_wide = True   # no history yet → assume OK
    checks[TradeQualityCheck.IB_WIDE] = ib_wide

    # --- Check 3: POC migration ---
    if open_poc is not None and config.value_step > 0:
        rows_moved = abs(profile.poc - open_poc) / config.value_step
        poc_migrated = rows_moved >= POC_MIGRATION_MIN
    else:
        poc_migrated = True   # no baseline yet → assume OK
    checks[TradeQualityCheck.POC_MIGRATED] = poc_migrated

    score = sum(checks.values())

    if score == 3:
        label, reason = "High", "All checks pass — normal trading conditions."
    elif score == 2:
        failed = [c.value for c, v in checks.items() if not v]
        label = "Marginal"
        reason = f"Reduce size — failing: {', '.join(failed)}."
    else:
        failed = [c.value for c, v in checks.items() if not v]
        label = "Skip"
        reason = f"Choppy/low-quality day — avoid directional trades. Failed: {', '.join(failed)}."

    return TradeQualityResult(score=score, checks=checks, label=label, reason=reason)

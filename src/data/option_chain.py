"""Live option chain fetch for the selected index's nearest expiry.

NOT NETWORK-VERIFIED: built without live access to Upstox's API, so the
endpoint/response shape below follows their publicly documented option
chain endpoint (`GET /v2/option/chain`) — verify against a real response
before trusting this in production.

SENSEX COVERAGE FLAG: Upstox's option chain coverage for BSE-listed SENSEX
options could not be confirmed in this offline build (no network access to
check current API docs or a live account/plan). Don't assume
`fetch_option_chain("BSE_INDEX|SENSEX", ...)` works until verified against
a real account — it may require a different exchange segment or simply be
unsupported on some plans. NIFTY/BANKNIFTY (NSE) are the well-documented
path.
"""

import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import requests

OPTION_CHAIN_URL = "https://api.upstox.com/v2/option/chain"

DEFAULT_POLL_INTERVAL_SECONDS = 4

logger = logging.getLogger(__name__)


def _parse_leg(leg_data: dict | None) -> dict | None:
    if not leg_data:
        return None
    market_data = leg_data.get("market_data", {})
    return {
        "ltp": market_data.get("ltp", 0.0),
        "oi": market_data.get("oi", 0),
        "volume": market_data.get("volume", 0),
        "iv": leg_data.get("option_greeks", {}).get("iv", 0.0),
    }


def parse_option_chain_response(payload: dict) -> list[dict]:
    """Upstox's documented option chain response is a list of per-strike
    rows under `data`, each with `call_options` / `put_options` sub-objects
    holding `market_data` (ltp, oi, volume) and `option_greeks` (iv)."""
    rows = []
    for entry in payload.get("data", []):
        rows.append(
            {
                "strike": entry["strike_price"],
                "CE": _parse_leg(entry.get("call_options")),
                "PE": _parse_leg(entry.get("put_options")),
            }
        )
    return sorted(rows, key=lambda row: row["strike"])


def nearest_weekly_expiry(today: dt.date | None = None) -> str:
    """NIFTY/BANKNIFTY weekly index options expire on Thursday (rolling to
    the prior trading day if Thursday is a holiday — holiday calendar
    adjustment is NOT handled here, just the plain weekday math).

    NOT VERIFIED: could not confirm SENSEX's current BSE weekly expiry
    weekday against live docs in this offline build — don't assume this
    function is correct for SENSEX without checking.
    """
    today = today or dt.date.today()
    days_until_thursday = (3 - today.weekday()) % 7  # Monday=0 ... Thursday=3
    expiry = today + dt.timedelta(days=days_until_thursday)
    return expiry.isoformat()


def fetch_option_chain(
    instrument_key: str, expiry_date: str, access_token: str
) -> list[dict]:
    """One-shot fetch of the current option chain snapshot."""
    response = requests.get(
        OPTION_CHAIN_URL,
        params={"instrument_key": instrument_key, "expiry_date": expiry_date},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return parse_option_chain_response(response.json())


@dataclass
class OptionChainPoller:
    """Polls the option chain on a fixed interval (default every 4s —
    snapshot-level frequency, not tick-level) and keeps the most recent
    and previous snapshot in memory for OI-buildup comparison.

    No history is persisted to disk in this session.
    """

    instrument_key: str
    expiry_date: str
    access_token: str
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    on_snapshot: Callable[[list[dict]], None] | None = None

    latest: list[dict] = field(default_factory=list)
    previous: list[dict] = field(default_factory=list)

    _thread: threading.Thread | None = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)

    def _poll_once(self) -> None:
        try:
            snapshot = fetch_option_chain(
                self.instrument_key, self.expiry_date, self.access_token
            )
        except Exception:
            logger.exception("Option chain poll failed")
            return
        self.previous = self.latest
        self.latest = snapshot
        if self.on_snapshot is not None:
            self.on_snapshot(snapshot)

    def _run(self) -> None:
        while self._running:
            self._poll_once()
            time.sleep(self.poll_interval_seconds)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)

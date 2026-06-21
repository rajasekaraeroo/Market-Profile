"""Upstox instrument key mapping for the index instruments this project
trades.

Upstox identifies instruments by `EXCHANGE_SEGMENT|trading_symbol` style
keys rather than plain names, and publishes the authoritative mapping as a
downloadable instrument master (JSON/CSV) at
https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz

NOT VERIFIED AGAINST THE LIVE MASTER: this build environment has no
outbound network access, so the keys below come from Upstox's public API
documentation rather than a fresh download of the instrument master. They
follow Upstox's documented format for index instruments. Before going
live, re-verify each key against the current instrument master file and
update `VERIFIED_DATE` below.
"""

VERIFIED_DATE = None  # e.g. "2024-06-01" once confirmed against the live master

INSTRUMENT_KEYS: dict[str, str] = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX",
}


def get_instrument_key(instrument_key: str) -> str:
    try:
        return INSTRUMENT_KEYS[instrument_key.upper()]
    except KeyError:
        raise ValueError(
            f"Unknown instrument '{instrument_key}'. "
            f"Available: {sorted(INSTRUMENT_KEYS)}"
        )

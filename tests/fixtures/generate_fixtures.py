"""One-off script that generated the synthetic OHLC fixtures in this folder.

Kept for reference / regenerating fixtures if the scenarios need tweaking —
not part of the test suite itself.
"""

import pandas as pd

FIXTURES_DIR = "tests/fixtures"


def _write(df: pd.DataFrame, name: str) -> None:
    df.to_csv(f"{FIXTURES_DIR}/{name}.csv", index_label="timestamp")


def make_balance_day() -> pd.DataFrame:
    """Price oscillates tightly between 24975 and 25025 all session.
    With value_step=25, this should produce a narrow profile centered
    around 25000."""
    timestamps = pd.date_range("2024-01-02 09:15", "2024-01-02 15:29", freq="1min")
    rows = []
    base = 25000
    wave = [0, 10, 20, 10, 0, -10, -20, -10]
    for i, ts in enumerate(timestamps):
        offset = wave[i % len(wave)]
        close = base + offset
        rows.append(
            {
                "timestamp": ts,
                "open": close,
                "high": close + 5,
                "low": close - 5,
                "close": close,
            }
        )
    return pd.DataFrame(rows).set_index("timestamp")


def make_trend_day() -> pd.DataFrame:
    """Price grinds steadily upward all session, IB at the day's low extreme.
    First hour (periods A, B) sits near the low; the rest of the day trends
    up with limited rotation back."""
    timestamps = pd.date_range("2024-01-03 09:15", "2024-01-03 15:29", freq="1min")
    rows = []
    base = 25000
    for i, ts in enumerate(timestamps):
        close = base + i * 4  # steady grind up across the session
        rows.append(
            {
                "timestamp": ts,
                "open": close,
                "high": close + 3,
                "low": close - 3,
                "close": close,
            }
        )
    return pd.DataFrame(rows).set_index("timestamp")


def make_partial_day() -> pd.DataFrame:
    """Only the first 3 TPO periods (09:15-10:45) of the balance day,
    simulating a mid-session snapshot."""
    full = make_balance_day()
    return full[full.index < pd.Timestamp("2024-01-02 10:45")]


if __name__ == "__main__":
    _write(make_balance_day(), "balance_day")
    _write(make_trend_day(), "trend_day")
    _write(make_partial_day(), "partial_day")

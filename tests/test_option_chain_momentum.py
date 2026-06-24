from src.data.option_chain import MOMENTUM_WINDOW_SECONDS, OptionChainPoller


def make_poller():
    return OptionChainPoller(
        instrument_key="NSE_INDEX|Nifty 50",
        expiry_date="2025-01-01",
        access_token="dummy",
    )


def test_update_momentum_flags_fresh_high():
    poller = make_poller()
    snapshot1 = [{"strike": 25000, "CE": {"ltp": 100.0}, "PE": {"ltp": 50.0}}]
    poller._update_momentum(snapshot1, now=0.0)
    assert snapshot1[0]["CE"]["momentum"] is False  # only one sample so far

    snapshot2 = [{"strike": 25000, "CE": {"ltp": 110.0}, "PE": {"ltp": 40.0}}]
    poller._update_momentum(snapshot2, now=10.0)
    assert snapshot2[0]["CE"]["momentum"] is True  # fresh high
    assert snapshot2[0]["PE"]["momentum"] is False  # lower than before


def test_update_momentum_prunes_samples_outside_window():
    poller = make_poller()
    snapshot1 = [{"strike": 25000, "CE": {"ltp": 200.0}, "PE": None}]
    poller._update_momentum(snapshot1, now=0.0)

    # A sample far enough in the future that the first one ages out of the
    # window should not be compared against it.
    snapshot2 = [{"strike": 25000, "CE": {"ltp": 100.0}, "PE": None}]
    poller._update_momentum(snapshot2, now=MOMENTUM_WINDOW_SECONDS + 1)
    assert snapshot2[0]["CE"]["momentum"] is False  # only sample left in window

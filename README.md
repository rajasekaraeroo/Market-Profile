# NSE Market Profile Tool

A desktop tool for building intraday Market Profile (TPO) charts on NSE
instruments (NIFTY / BANKNIFTY / stocks), with a live option-chain overlay,
to support discretionary options trading decisions.

> ⚠️ **Disclaimer**: This tool is for educational and analytical purposes
> only. It does not provide investment advice or trading signals that
> guarantee profit. Options trading carries substantial risk of loss.
> Past performance of any indicator (POC, Value Area, IB) does not
> guarantee future results. Consult a SEBI-registered advisor before
> making investment decisions.

## What it does

- Builds 30-minute TPO (Time Price Opportunity) profiles from intraday
  1-minute / tick data
- Computes Point of Control (POC), Value Area (VA), and Initial Balance (IB)
- Classifies day type as it develops (balance / trend / neutral)
- Overlays live option chain data (OI, IV, OI change) on the underlying's
  profile
- Renders profile + option chain in a PyQt5 desktop UI
- Sends Telegram alerts on IB breakout, VA rejection, and POC migration

## Architecture

```
market-profile-tool/
├── src/
│   ├── data/           # Upstox historical + WebSocket feed handlers
│   ├── engine/         # TPO / POC / VA / IB computation (pure Python, no UI)
│   ├── ui/             # PyQt5 widgets (profile chart, option chain panel)
│   ├── alerts/          # Telegram notification layer
│   └── config/         # Instrument configs (tick size, lot size, IB window)
├── tests/              # Unit tests for the engine, run against known sessions
├── data/                # Local cache of historical sessions (gitignored)
├── .env.example         # Template for API credentials
├── requirements.txt
└── main.py
```

## Setup

1. Clone the repo and create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your Upstox API key, secret,
   and redirect URI (never commit `.env`).
3. Run `python main.py` to launch the desktop app.

## Status

Early scaffolding stage — engine and data layers being built session by
session via Claude Code. See `docs/sessions/` (added as work progresses)
for the spec used in each build session.

## License

MIT — see `LICENSE`.

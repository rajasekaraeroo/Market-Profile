"""Upstox OAuth2 login flow and access-token storage.

Upstox access tokens are valid only for the trading day (they expire at
end of day / early next morning IST) and Upstox does not support silent
refresh — a human has to complete the redirect login once per day. This
module implements that flow and caches the resulting token locally so the
rest of the data layer can just call `get_access_token()`.

Run interactively once a day with:

    python -m src.data.upstox_auth
"""

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import requests

AUTH_BASE_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

# Upstox tokens are invalidated daily; we treat any token not obtained
# "today" (IST) as stale rather than trying to parse an exact expiry.
TOKEN_FILE = Path(os.environ.get("UPSTOX_TOKEN_FILE", ".upstox_token.json"))


@dataclass
class StoredToken:
    access_token: str
    obtained_on: str  # ISO date (IST) the token was issued


def _today_ist() -> str:
    ist_now = dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)
    return ist_now.date().isoformat()


def build_login_url(api_key: str, redirect_uri: str) -> str:
    """URL the user opens in a browser to start the OAuth redirect flow."""
    params = {
        "response_type": "code",
        "client_id": api_key,
        "redirect_uri": redirect_uri,
    }
    return f"{AUTH_BASE_URL}?{urlencode(params)}"


def exchange_code_for_token(
    api_key: str, api_secret: str, redirect_uri: str, code: str
) -> str:
    """Exchange the authorization code (from the redirect callback) for an
    access token."""
    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": api_key,
            "client_secret": api_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    return payload["access_token"]


def save_token(access_token: str) -> None:
    TOKEN_FILE.write_text(
        json.dumps({"access_token": access_token, "obtained_on": _today_ist()})
    )


def load_token() -> StoredToken | None:
    if not TOKEN_FILE.exists():
        return None
    data = json.loads(TOKEN_FILE.read_text())
    return StoredToken(**data)


def is_token_fresh(token: StoredToken) -> bool:
    return token.obtained_on == _today_ist()


def get_access_token() -> str:
    """Return today's cached access token, or raise if none is fresh.

    Callers should catch the error and direct the user to run
    `python -m src.data.upstox_auth` to re-authenticate.
    """
    token = load_token()
    if token is None or not is_token_fresh(token):
        raise RuntimeError(
            "No valid Upstox access token for today. "
            "Run `python -m src.data.upstox_auth` to log in."
        )
    return token.access_token


def _run_cli_login() -> None:
    api_key = os.environ["UPSTOX_API_KEY"]
    api_secret = os.environ["UPSTOX_API_SECRET"]
    redirect_uri = os.environ["UPSTOX_REDIRECT_URI"]

    login_url = build_login_url(api_key, redirect_uri)
    print("Open this URL in a browser and log in:\n")
    print(login_url)
    print(
        "\nAfter login, Upstox redirects to your redirect_uri with "
        "?code=<...> in the query string. Paste that code below."
    )
    code = input("Authorization code: ").strip()

    access_token = exchange_code_for_token(api_key, api_secret, redirect_uri, code)
    save_token(access_token)
    print(f"Access token saved to {TOKEN_FILE} (valid for today only).")


if __name__ == "__main__":
    _run_cli_login()

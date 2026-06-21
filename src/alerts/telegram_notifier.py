"""Thin wrapper around the Telegram Bot API send-message call.

A failed Telegram send must never take down the live feed or UI — network
errors are logged and swallowed, not raised.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_alert(message: str) -> bool:
    """Send `message` to the configured Telegram chat. Returns True on
    success, False on any failure (already logged)."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured; dropping alert: %s", message)
        return False

    try:
        response = requests.post(
            TELEGRAM_API_URL.format(token=bot_token),
            data={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send Telegram alert: %s", message)
        return False

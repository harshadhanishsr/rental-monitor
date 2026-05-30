"""Minimal Telegram sender for v2 alerts.

Only the ``sendMessage`` path with inline-keyboard tracking buttons is
needed by the engine — the polling loop / tracker summary lives in
``legacy/notifier/tracker_bot.py`` until the v2 button handler ships.
"""
from __future__ import annotations
import logging
import os
import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _chat_id() -> str:
    return os.environ["TELEGRAM_CHAT_ID"]


def send_with_buttons(text: str, tracking_id: str) -> int | None:
    """Send a listing alert with [⭐][📞][👎] tracking buttons.

    Returns the Telegram ``message_id`` or ``None`` on failure.
    """
    keyboard = {
        "inline_keyboard": [[
            {"text": "⭐ Shortlist",  "callback_data": f"s:{tracking_id}"},
            {"text": "📞 Contacted", "callback_data": f"c:{tracking_id}"},
            {"text": "👎 Pass",      "callback_data": f"p:{tracking_id}"},
        ]]
    }
    url = _BASE.format(token=_token(), method="sendMessage")
    try:
        r = requests.post(url, json={
            "chat_id": _chat_id(),
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
            "reply_markup": keyboard,
        }, timeout=10)
        r.raise_for_status()
        return r.json().get("result", {}).get("message_id")
    except Exception:
        logger.exception("Telegram sendMessage failed")
        return None

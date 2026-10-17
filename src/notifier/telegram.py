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


def send_with_buttons(text: str, tracking_id: str,
                       photo_url: str | None = None) -> int | None:
    """Send a listing alert with [⭐][📞][👎] tracking buttons.

    If ``photo_url`` is given, posts via ``sendPhoto`` with ``text`` as the
    caption; falls back to ``sendMessage`` if the photo upload is rejected
    (e.g. Telegram couldn't fetch the URL).

    Returns the Telegram ``message_id`` or ``None`` on failure.
    """
    keyboard = {
        "inline_keyboard": [[
            {"text": "⭐ Shortlist",  "callback_data": f"s:{tracking_id}"},
            {"text": "📞 Contacted", "callback_data": f"c:{tracking_id}"},
            {"text": "👎 Pass",      "callback_data": f"p:{tracking_id}"},
        ]]
    }
    token = _token()
    chat = _chat_id()

    def _send_text() -> "requests.Response":
        return requests.post(
            _BASE.format(token=token, method="sendMessage"),
            json={
                "chat_id": chat, "text": text, "parse_mode": "Markdown",
                "disable_web_page_preview": False, "reply_markup": keyboard,
            },
            timeout=10,
        )

    try:
        if photo_url:
            r = requests.post(
                _BASE.format(token=token, method="sendPhoto"),
                json={
                    "chat_id": chat, "photo": photo_url, "caption": text,
                    "parse_mode": "Markdown", "reply_markup": keyboard,
                },
                timeout=10,
            )
            if not r.ok:
                # Telegram couldn't fetch the image — fall back to text.
                r = _send_text()
        else:
            r = _send_text()
        r.raise_for_status()
        return r.json().get("result", {}).get("message_id")
    except Exception:
        logger.exception("Telegram send failed")
        return None

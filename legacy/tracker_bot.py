"""
Telegram inline-button tracker.

Each listing alert is sent with three buttons:
  [⭐ Shortlist]  [📞 Contacted]  [👎 Pass]

Tapping a button:
  - Instantly edits the message to show the new status
  - Stores the status in SQLite

Bot commands:
  /summary   — shows all shortlisted + contacted listings
  /shortlist — shortlisted only
"""
import logging
import os
import sqlite3
import threading
import time
import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"
_STATUS_LABEL = {
    "shortlisted": "⭐ Shortlisted",
    "contacted":   "📞 Contacted",
    "passed":      "👎 Passed",
}
_STATUS_EMOJI = {
    "shortlisted": "⭐",
    "contacted":   "📞",
    "passed":      "👎",
}


def _token():
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _chat_id():
    return os.environ["TELEGRAM_CHAT_ID"]


def _api(method, **kwargs):
    url = _BASE.format(token=_token(), method=method)
    try:
        r = requests.post(url, json=kwargs, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception("Telegram API error: %s", method)
        return {}


def send_with_buttons(text: str, tracking_id: str) -> int | None:
    """Send a listing alert with tracking buttons. Returns message_id."""
    keyboard = {
        "inline_keyboard": [[
            {"text": "⭐ Shortlist",  "callback_data": f"s:{tracking_id}"},
            {"text": "📞 Contacted", "callback_data": f"c:{tracking_id}"},
            {"text": "👎 Pass",      "callback_data": f"p:{tracking_id}"},
        ]]
    }
    resp = _api(
        "sendMessage",
        chat_id=_chat_id(),
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=False,
        reply_markup=keyboard,
    )
    result = resp.get("result", {})
    return result.get("message_id")


def _edit_status(msg_id: int, original_text: str, status: str):
    """Replace buttons with a status line and answer the callback."""
    label = _STATUS_LABEL.get(status, status)
    new_text = original_text + f"\n\n*Status: {label}*"
    _api(
        "editMessageText",
        chat_id=_chat_id(),
        message_id=msg_id,
        text=new_text,
        parse_mode="Markdown",
        disable_web_page_preview=False,
    )


def _answer_callback(callback_id: str, text: str):
    _api("answerCallbackQuery", callback_query_id=callback_id, text=text, show_alert=False)


def _handle_summary(conn: sqlite3.Connection, command: str):
    from src.db import tracker_summary
    data = tracker_summary(conn)

    if command in ("/shortlist", "/shortlisted"):
        sections = {"shortlisted": data["shortlisted"]}
        header = "⭐ *Your Shortlisted Listings*"
    else:
        sections = data
        header = "📋 *Your Listing Tracker*"

    lines = [header, ""]
    total = sum(len(v) for v in sections.values())

    if total == 0:
        lines.append("Nothing tracked yet. Tap ⭐ / 📞 / 👎 on any listing.")
    else:
        for status, items in sections.items():
            if not items:
                continue
            emoji = _STATUS_EMOJI.get(status, "")
            lines.append(f"{emoji} *{status.title()}* ({len(items)})")
            for item in items:
                price = f"₹{item['price']:,}" if item.get("price") else "?"
                dist  = f"{item['dist_km']:.1f}km" if item.get("dist_km") else ""
                mins  = f"{item['transit_mins']:.0f}min" if item.get("transit_mins") else ""
                commute = f" | {mins} transit" if mins else ""
                lines.append(
                    f"  • {item['address']} — {price}{commute}\n"
                    f"    {item['url']}"
                )
            lines.append("")

    _api(
        "sendMessage",
        chat_id=_chat_id(),
        text="\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


_ACTION_MAP = {"s": "shortlisted", "c": "contacted", "p": "passed"}
_ACTION_TOAST = {
    "shortlisted": "⭐ Added to shortlist!",
    "contacted":   "📞 Marked as contacted!",
    "passed":      "👎 Marked as passed.",
}


def start_polling(conn: sqlite3.Connection):
    """Start bot polling in a background daemon thread."""
    t = threading.Thread(target=_poll_loop, args=(conn,), daemon=True)
    t.start()
    logger.info("Tracker bot polling started.")


def _poll_loop(conn: sqlite3.Connection):
    from src.db import tracker_set_status, tracker_get
    offset = None

    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["callback_query", "message"]}
            if offset:
                params["offset"] = offset

            resp = requests.get(
                _BASE.format(token=_token(), method="getUpdates"),
                params=params,
                timeout=40,
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1

                # ── Button tap ────────────────────────────────
                if "callback_query" in update:
                    cq      = update["callback_query"]
                    cb_id   = cq["id"]
                    data    = cq.get("data", "")
                    msg     = cq.get("message", {})
                    msg_id  = msg.get("message_id")
                    orig    = msg.get("text", "")

                    parts = data.split(":", 1)
                    if len(parts) == 2 and parts[0] in _ACTION_MAP:
                        action      = _ACTION_MAP[parts[0]]
                        tracking_id = parts[1]

                        tracker_set_status(conn, tracking_id, action)
                        _answer_callback(cb_id, _ACTION_TOAST[action])
                        if msg_id:
                            _edit_status(msg_id, orig, action)
                        logger.info("Tracked %s → %s", tracking_id[:12], action)

                # ── Text command ──────────────────────────────
                elif "message" in update:
                    text = update["message"].get("text", "").strip().lower()
                    if text in ("/summary", "/shortlist", "/shortlisted"):
                        _handle_summary(conn, text)

        except Exception:
            logger.exception("Polling error — retrying in 5s")
            time.sleep(5)

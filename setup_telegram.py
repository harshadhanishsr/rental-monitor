"""
One-time Telegram bot setup helper.

Run this AFTER you have a bot token from @BotFather and have sent
your bot at least one message.

Usage:
    python setup_telegram.py --token YOUR_BOT_TOKEN
"""
import argparse
import requests
import sys


def get_chat_id(token: str) -> int | None:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    r = requests.get(url, timeout=10)
    data = r.json()
    if not data.get("ok"):
        print("Error:", data.get("description", "Unknown error"))
        return None
    updates = data.get("result", [])
    if not updates:
        print("No messages found yet.")
        print("Please send any message (e.g. 'hi') to your bot in Telegram, then re-run this script.")
        return None
    chat_id = updates[-1]["message"]["chat"]["id"]
    return chat_id


def send_test(token: str, chat_id: int) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={
        "chat_id": chat_id,
        "text": "✅ Rental Monitor connected! You will receive listing alerts here.",
    }, timeout=10)
    return r.json().get("ok", False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="Bot token from @BotFather")
    args = parser.parse_args()

    token = args.token.strip()
    print(f"Checking bot token...")

    chat_id = get_chat_id(token)
    if chat_id is None:
        sys.exit(1)

    print(f"\nSuccess! Your chat ID is: {chat_id}")
    print(f"\nAdd these two lines to your .env file:")
    print(f"  TELEGRAM_BOT_TOKEN={token}")
    print(f"  TELEGRAM_CHAT_ID={chat_id}")

    print("\nSending test message...")
    if send_test(token, chat_id):
        print("Test message sent! Check Telegram.")
    else:
        print("Test message failed — double-check the token.")


if __name__ == "__main__":
    main()

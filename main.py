import logging
import os
import time
from dotenv import load_dotenv
from src.db import init_db, get_connection
from src.notifier.whatsapp import health_check as _whatsapp_health
from src.notifier import telegram_bot as _tg
import os


def health_check():
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        return _tg.health_check()
    return _whatsapp_health()
from src.scheduler import run_cycle

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/app/data/rental_monitor.db")
OFFICE_LAT = float(os.environ.get("OFFICE_LAT", "12.9698"))
OFFICE_LNG = float(os.environ.get("OFFICE_LNG", "80.1409"))
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "3600"))


def main():
    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Running startup WhatsApp health-check...")
    ok = health_check()
    if not ok:
        logger.warning(
            "Startup health-check FAILED. Twilio sandbox may have expired. "
            "Re-send the join message from your phone, then restart the container."
        )

    if ok:
        logger.info("Running first cycle immediately...")
        run_cycle(conn, OFFICE_LAT, OFFICE_LNG)

    logger.info("Scheduler started. Checking every %d seconds.", INTERVAL_SECONDS)
    while True:
        time.sleep(INTERVAL_SECONDS)
        logger.info("Starting scheduled cycle...")
        try:
            run_cycle(conn, OFFICE_LAT, OFFICE_LNG)
        except Exception:
            logger.exception("Unhandled error in scheduled cycle — will retry next interval")


if __name__ == "__main__":
    main()

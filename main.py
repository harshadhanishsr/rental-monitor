import logging
import os
from dotenv import load_dotenv

load_dotenv()

import os
from config import OFFICE_LAT, OFFICE_LNG, CHECK_INTERVAL_SECONDS
from src.db import init_db, get_connection
from src.scheduler import run_cycle
from src.notifier import telegram_bot as _tg
from src.notifier.whatsapp import health_check as _whatsapp_health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH          = os.environ.get("DB_PATH", "data/rental_monitor.db")
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", str(CHECK_INTERVAL_SECONDS)))


def health_check():
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        return _tg.health_check()
    return _whatsapp_health()


def main():
    import time
    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Running startup health-check…")
    ok = health_check()
    if not ok:
        logger.warning(
            "Startup health-check FAILED. "
            "Check your Telegram/Twilio credentials in .env"
        )

    if ok:
        logger.info("Running first cycle immediately…")
        run_cycle(conn, OFFICE_LAT, OFFICE_LNG)

    logger.info("Scheduler started — checking every %d seconds.", INTERVAL_SECONDS)
    while True:
        time.sleep(INTERVAL_SECONDS)
        logger.info("Starting scheduled cycle…")
        try:
            run_cycle(conn, OFFICE_LAT, OFFICE_LNG)
        except Exception:
            logger.exception("Unhandled error in cycle — will retry next interval")


if __name__ == "__main__":
    main()

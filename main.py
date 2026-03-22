import logging
import os
import sqlite3
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from src.db import init_db, get_connection
from src.notifier.whatsapp import health_check
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


def main():
    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Running startup WhatsApp health-check...")
    ok = health_check()
    if not ok:
        logger.warning(
            "Startup health-check FAILED. Twilio sandbox may have expired. "
            "Re-send the join message from your phone, then restart the container. "
            "Skipping first scrape cycle — will retry in 1 hour."
        )

    scheduler = BlockingScheduler()
    scheduler.add_job(
        func=lambda: run_cycle(conn, OFFICE_LAT, OFFICE_LNG),
        trigger="interval",
        hours=1,
        max_instances=1,
        id="rental_monitor",
        name="Rental Monitor Hourly Run",
    )

    if ok:
        logger.info("Running first cycle immediately...")
        run_cycle(conn, OFFICE_LAT, OFFICE_LNG)

    logger.info("Scheduler started. Checking every hour.")
    scheduler.start()


if __name__ == "__main__":
    main()

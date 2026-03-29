"""
Single-cycle runner for GitHub Actions.
Runs one scrape cycle and exits — called by the hourly workflow.
"""
import io
import logging
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/monitor.log", encoding="utf-8"),
    ],
)

from src.db import init_db, get_connection
from monitor import run_cycle

DB_PATH = os.environ.get("DB_PATH", "data/rental_monitor.db")

if __name__ == "__main__":
    conn = get_connection(DB_PATH)
    init_db(conn)
    run_cycle(conn)
    conn.close()

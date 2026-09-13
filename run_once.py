"""Single-cycle runner (called by the hourly GitHub Action).

Usage::

    uv run python run_once.py          # one scrape+alert cycle
    uv run python run_once.py --digest # send the daily digest
"""
from __future__ import annotations
import asyncio
import io
import logging
import os
import sys
from pathlib import Path

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

from src.core.engine import EngineConfig, run_cycle
from src.notifier.alert_v2 import alert
from src.sources.registry import all_sources


def main() -> int:
    db_path = Path(os.environ.get("DB_PATH", "data/rental_monitor.db"))
    if "--digest" in sys.argv:
        from src.notifier.digest import run_digest
        asyncio.run(run_digest(db_path))
        return 0
    cfg = EngineConfig(
        db_path=db_path,
        sources=all_sources(),
        deadline_s=90,
        alert_fn=alert,
        proxy=os.environ.get("PROXY_URL") or None,
    )
    asyncio.run(run_cycle(cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

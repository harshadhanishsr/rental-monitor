"""Long-running monitor — sleeps ``CHECK_INTERVAL_SECONDS`` between cycles.

Thin loop around ``run_once.main()`` so a single binary covers both the
one-shot GitHub Action path and the long-running local mode.
"""
from __future__ import annotations
import logging
import time

from config import CHECK_INTERVAL_SECONDS
from run_once import main as run_once_main

logger = logging.getLogger("monitor")


def main() -> None:
    while True:
        try:
            run_once_main()
        except Exception:
            logger.exception("cycle failed — retrying next interval")
        logger.info("sleeping %ds until next cycle", CHECK_INTERVAL_SECONDS)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

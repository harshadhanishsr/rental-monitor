from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
from src.core.circuit import Breaker, BreakerOpen
from src.core.http import AsyncHttp
from src.core.ratelimit import TokenBucket
from src.models import Listing, RunStats
from src.pipeline.dedup import fingerprint, merge
from src.sources.base import SourceAdapter, SourceCtx
from src.state.db import connect, migrate

logger = logging.getLogger("engine")


@dataclass
class EngineConfig:
    db_path: Path
    sources: list[SourceAdapter]
    deadline_s: float = 90
    alert_fn: Callable[[Listing, RunStats], Awaitable[int | None]] | None = None
    proxy: str | None = None


async def _run_source(source: SourceAdapter, ctx: SourceCtx,
                      out: asyncio.Queue, deadline: float, stats: RunStats) -> None:
    name = source.name
    stats.per_source[name] = {"scraped": 0, "kept": 0, "errored": 0, "ms": 0}
    t0 = time.monotonic()
    try:
        ctx.breaker.check()
        async with asyncio.timeout(deadline):
            async for listing in source.scrape(ctx):
                stats.per_source[name]["scraped"] += 1
                await out.put(listing)
        ctx.breaker.record_success()
    except BreakerOpen:
        stats.breaker_open.append(name)
        logger.warning("[%s] breaker open — skipped", name)
    except Exception as e:
        ctx.breaker.record_failure()
        stats.per_source[name]["errored"] += 1
        logger.exception("[%s] failed: %s", name, e)
    finally:
        stats.per_source[name]["ms"] = int((time.monotonic() - t0) * 1000)


async def run_cycle(cfg: EngineConfig) -> RunStats:
    stats = RunStats(started_at=int(time.time()))
    t0 = time.monotonic()
    queue: asyncio.Queue[Listing | None] = asyncio.Queue()
    fingerprints: dict[str, list[Listing]] = {}

    async with AsyncHttp(proxy=cfg.proxy) as http, \
               connect(cfg.db_path) as db:
        await migrate(db)
        ctxs = [
            SourceCtx(
                http=http,
                bucket=TokenBucket(s.rate.rate, s.rate.burst),
                breaker=Breaker(),
                logger=logger.getChild(s.name),
                config=None,
            ) for s in cfg.sources
        ]

        async def consume_and_dedup():
            while True:
                l = await queue.get()
                if l is None:
                    break
                fp = fingerprint(l)
                l = l.model_copy(update={"fingerprint": fp})
                fingerprints.setdefault(fp, []).append(l)
                stats.raw_count += 1

        consumer = asyncio.create_task(consume_and_dedup())

        async with asyncio.TaskGroup() as tg:
            for s, ctx in zip(cfg.sources, ctxs):
                tg.create_task(_run_source(s, ctx, queue, cfg.deadline_s, stats))

        await queue.put(None)
        await consumer

        deduped = [merge(group) for group in fingerprints.values()]
        stats.after_filter = stats.raw_count
        stats.after_dedup = len(deduped)

        if cfg.alert_fn:
            for l in deduped:
                msg_id = await cfg.alert_fn(l, stats)
                if msg_id is not None:
                    stats.alerted += 1

        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        await db.execute(
            "INSERT INTO runs (started_at,duration_ms,raw_count,after_filter,"
            "after_dedup,alerted,per_source,breaker_open) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (stats.started_at, stats.duration_ms, stats.raw_count,
             stats.after_filter, stats.after_dedup, stats.alerted,
             json.dumps(stats.per_source), json.dumps(stats.breaker_open)))
        await db.commit()
    return stats

from __future__ import annotations
import re
import urllib.parse
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

# Matches one DDG /html result block: redirect-wrapped href + visible title + snippet.
_RESULT = re.compile(
    r'class="result__a"[^>]+href="//duckduckgo\.com/l/\?uddg=([^"&]+)[^"]*"[^>]*>([^<]+)</a>'
    r'(?:.*?class="result__snippet"[^>]*>(.*?)</(?:a|div)>)?',
    re.S,
)
_PRICE = re.compile(
    r"(?:\u20b9|Rs\.?|INR)\s*([\d,]{4,6})|"
    r"([\d,]{4,6})\s*(?:/month|per month|\s*pm|/mo)\b",
    re.I,
)
_TAG = re.compile(r"<[^>]+>")

_DOMAINS = (
    ("nobroker.in/property/", "nobroker"),
    ("olx.in/item/", "olx"),
    ("magicbricks.com/property-details/", "magicbricks"),
    ("housing.com/listing/", "housing"),
    ("housing.com/property/", "housing"),
    ("99acres.com/", "99acres"),
    ("sulekha.com/", "sulekha"),
    ("quikr.com/homes/", "quikr"),
)


def _is_listing_url(url: str) -> str | None:
    for needle, src in _DOMAINS:
        if needle in url:
            return src
    return None


def _strip(text: str) -> str:
    return _TAG.sub("", text or "").strip()


def _extract_price(text: str) -> int | None:
    m = _PRICE.search(text)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        return int(raw.replace(",", ""))
    except (ValueError, AttributeError):
        return None


class DuckDuckGo(SourceAdapter):
    """Meta-discovery source: hits DDG's /html endpoint to surface URLs
    pointing at the other property sites. All results are tagged
    ``source='duckduckgo'`` so the dedupe layer can fold them into the
    canonical listing's ``also_seen_on``."""

    name = "duckduckgo"
    rate = RateLimit(rate=0.3, burst=2)

    def _queries(self, cfg) -> list[str]:
        from config import MAX_RENT, PROPERTY_SLUG, SEARCH_AREAS
        beds = PROPERTY_SLUG[0]
        out: list[str] = []
        for area in SEARCH_AREAS:
            out.append(f"{beds} BHK apartment for rent in {area} site:nobroker.in")
            out.append(f"{area} {beds} bhk rent under {MAX_RENT}")
        return out

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome110") as session:
            seen: set[str] = set()
            for q in self._queries(ctx.config):
                ctx.breaker.check()
                await ctx.bucket.acquire()
                try:
                    r = await session.post(
                        "https://html.duckduckgo.com/html/",
                        data={"q": q, "kl": "in-en"},
                        headers={"Accept-Language": "en-IN,en;q=0.9",
                                 "Referer": "https://duckduckgo.com/"},
                    )
                except Exception:
                    ctx.breaker.record_failure()
                    continue
                if r.status_code != 200:
                    continue
                for listing in self._parse(r.text):
                    if listing.url in seen:
                        continue
                    seen.add(listing.url)
                    yield listing

    def _parse(self, html: str) -> list[Listing]:
        from config import CITY, MAX_RENT, MIN_RENT
        out: list[Listing] = []
        for m in _RESULT.finditer(html):
            raw_url = urllib.parse.unquote(m.group(1))
            origin = _is_listing_url(raw_url)
            if not origin:
                continue
            title = _strip(m.group(2))
            snippet = _strip(m.group(3) or "")
            price = _extract_price(snippet) or _extract_price(title)
            if not price or not (MIN_RENT <= price <= MAX_RENT):
                continue
            # DDG can't tell us address; use the search city as a coarse anchor.
            address = CITY
            # Use the URL itself as a stable id; the dedupe layer will fold
            # any same-fingerprint sibling from the origin source.
            listing_id = f"ddg_{abs(hash(raw_url)) % (10**12):012d}"
            out.append(Listing(
                id=listing_id, source="duckduckgo",
                title=title[:120], address=address, price=price,
                url=raw_url, also_seen_on=[origin],
            ))
        return out

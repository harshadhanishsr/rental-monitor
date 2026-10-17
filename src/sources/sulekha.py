from __future__ import annotations
import json
import re
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)
_PRICE = re.compile(r"(?:Rent|₹|Rs\.?|INR)[^₹\d]{0,15}([\d,]{4,6})")
_ID = re.compile(r"-(\d{6,})-ad$")


class Sulekha(SourceAdapter):
    name = "sulekha"
    rate = RateLimit(rate=1.0, burst=3)

    def _urls(self, cfg) -> list[str]:
        from config import SEARCH_AREAS, CITY, PROPERTY_SLUG
        beds = PROPERTY_SLUG[0]
        city = CITY.lower()
        return [
            f"https://property.sulekha.com/{beds}-bhk-apartments-flats-for-rent/{city}/{a.lower().replace(' ', '-')}"
            for a in SEARCH_AREAS
        ]

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        seen_ids: set[str] = set()
        for url in self._urls(ctx.config):
            ctx.breaker.check()
            await ctx.bucket.acquire()
            r = await ctx.http.get(url, headers={"Referer": "https://property.sulekha.com/"})
            if r.status_code not in (200, 206):
                continue
            for listing in self._parse(r.text):
                if listing.id in seen_ids:
                    continue
                seen_ids.add(listing.id)
                yield listing

    def _parse(self, html: str) -> list[Listing]:
        from config import MIN_RENT, MAX_RENT, CITY
        out: list[Listing] = []
        for m in _JSON_LD.finditer(html):
            try:
                data = json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                continue
            for item in (data if isinstance(data, list) else [data]):
                t = item.get("@type", [])
                if isinstance(t, str):
                    t = [t]
                if not any(x in t for x in ("Apartment", "House", "Product")):
                    continue
                url = item.get("url", "")
                if "sulekha" not in url:
                    continue
                m_id = _ID.search(url)
                listing_id = m_id.group(1) if m_id else url[-12:]
                offers = item.get("offers") or {}
                price = None
                if isinstance(offers, dict):
                    p = offers.get("price") or offers.get("lowPrice")
                    if p:
                        try:
                            price = int(str(p).replace(",", ""))
                        except ValueError:
                            pass
                if not price:
                    pm = _PRICE.search(item.get("description", "") + item.get("name", ""))
                    if pm:
                        price = int(pm.group(1).replace(",", ""))
                if not price or not (MIN_RENT <= price <= MAX_RENT):
                    continue
                geo = item.get("geo") or {}
                try:
                    lat = float(geo.get("latitude") or 0) or None
                    lng = float(geo.get("longitude") or 0) or None
                except (ValueError, TypeError):
                    lat = lng = None
                address = str(item.get("address") or "")
                if CITY.lower() not in address.lower():
                    address = f"{address}, {CITY}".strip(", ")
                out.append(Listing(
                    id=f"sulekha_{listing_id}", source="sulekha",
                    title=str(item.get("name") or "1 BHK")[:120],
                    address=address, price=price, url=url,
                    lat=lat, lng=lng,
                ))
        return out

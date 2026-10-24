from __future__ import annotations
import json
import re
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

# Listing cards expose all key fields in data-* attributes on a wrapper div.
_CARD = re.compile(
    r'<div\s+class="favorite-btn[^"]*"([^>]+)>', re.S)
_ATTR = re.compile(r'data-([a-zA-Z]+)="([^"]*)"')

# JSON-LD blocks carry lat/lng for each card (matched by propertyid embedded in URL).
_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)
_URL_ID = re.compile(r"/(\d{5,})(?:/|$)")


class SquareYards(SourceAdapter):
    name = "squareyards"
    rate = RateLimit(rate=1.0, burst=3)

    def _urls(self, cfg) -> list[str]:
        from config import SEARCH_AREAS, CITY, PROPERTY_SLUG
        beds = PROPERTY_SLUG[0]
        city_slug = CITY.lower().replace(" ", "-")
        return [
            f"https://www.squareyards.com/rent/{beds}-bhk-for-rent-in-{a.lower().replace(' ', '-')}-{city_slug}"
            for a in SEARCH_AREAS
        ]

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        seen_ids: set[str] = set()
        for url in self._urls(ctx.config):
            ctx.breaker.check()
            await ctx.bucket.acquire()
            r = await ctx.http.get(url, headers={"Referer": "https://www.squareyards.com/"})
            if r.status_code not in (200, 206):
                continue
            for listing in self._parse(r.text):
                if listing.id in seen_ids:
                    continue
                seen_ids.add(listing.id)
                yield listing

    def _geo_by_id(self, html: str) -> dict[str, tuple[float, float]]:
        out: dict[str, tuple[float, float]] = {}
        for m in _JSON_LD.finditer(html):
            try:
                data = json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                continue
            for item in (data if isinstance(data, list) else [data]):
                url = str(item.get("url") or "")
                m_id = _URL_ID.search(url)
                if not m_id:
                    continue
                geo = item.get("geo") or {}
                try:
                    lat = float(geo.get("latitude") or 0) or None
                    lng = float(geo.get("longitude") or 0) or None
                except (ValueError, TypeError):
                    lat = lng = None
                if lat is not None and lng is not None:
                    out[m_id.group(1)] = (lat, lng)
        return out

    def _parse(self, html: str) -> list[Listing]:
        from config import MIN_RENT, MAX_RENT, CITY
        out: list[Listing] = []
        geo_map = self._geo_by_id(html)
        for card in _CARD.finditer(html):
            attrs = dict(_ATTR.findall(card.group(1)))
            try:
                price = int(attrs.get("price", "0"))
            except ValueError:
                continue
            if not (MIN_RENT <= price <= MAX_RENT):
                continue
            url = attrs.get("url", "")
            if "squareyards" not in url:
                continue
            m_id = _URL_ID.search(url)
            listing_id = m_id.group(1) if m_id else url[-12:]
            address = attrs.get("locality") or attrs.get("sublocalityname") or ""
            if CITY.lower() not in address.lower():
                address = f"{address}, {CITY}".strip(", ")
            lat, lng = geo_map.get(listing_id, (None, None))
            images: list[str] = []
            img = attrs.get("image")
            if img:
                images = [img]
            out.append(Listing(
                id=f"squareyards_{listing_id}", source="squareyards",
                title=(attrs.get("name") or "1 BHK")[:120],
                address=address, price=price, url=url,
                lat=lat, lng=lng, images=images,
            ))
        return out

from __future__ import annotations
import json
import re
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

# Listings are server-rendered into window.SERVER_PRELOADED_STATE_.nsrResultList.
_STATE = re.compile(
    r"window\.SERVER_PRELOADED_STATE_\s*=\s*(\{.*?\});\s*(?:window\.|</script>|var\s)",
    re.S,
)


class MagicBricks(SourceAdapter):
    name = "magicbricks"
    rate = RateLimit(rate=0.5, burst=2)
    needs_browser = False

    def _urls(self, cfg) -> list[str]:
        from config import SEARCH_AREAS, PROPERTY_SLUG, CITY
        beds = PROPERTY_SLUG[0]
        city = CITY.lower().replace(" ", "-")
        return [
            f"https://www.magicbricks.com/{beds}-bhk-flats-for-rent-in-{a.lower().replace(' ', '-')}-{city}-pppfr"
            for a in SEARCH_AREAS
        ]

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome110") as session:
            seen: set[str] = set()
            for url in self._urls(ctx.config):
                ctx.breaker.check()
                await ctx.bucket.acquire()
                try:
                    r = await session.get(
                        url, headers={"Accept-Language": "en-IN,en;q=0.9",
                                      "Referer": "https://www.magicbricks.com/"})
                except Exception:
                    ctx.breaker.record_failure()
                    continue
                if r.status_code != 200:
                    continue
                for listing in self._parse(r.text):
                    if listing.id in seen:
                        continue
                    seen.add(listing.id)
                    yield listing

    def _parse(self, html: str) -> list[Listing]:
        from config import CITY, MAX_RENT, MIN_RENT
        m = _STATE.search(html)
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []
        items = data.get("nsrResultList") or data.get("searchResult") or []
        out: list[Listing] = []
        for it in items:
            try:
                price = int(it.get("price") or it.get("minPrice") or 0)
            except (TypeError, ValueError):
                continue
            if not (MIN_RENT <= price <= MAX_RENT):
                continue
            listing_id = str(it.get("id") or "")
            if not listing_id:
                continue
            seo_url = it.get("seoURL") or it.get("url") or ""
            if seo_url and not seo_url.startswith("http"):
                seo_url = f"https://www.magicbricks.com/{seo_url.lstrip('/')}"
            # MagicBricks' seoURL uses '&' as the first separator instead of '?'.
            # Fix it so the query string parses correctly in browsers.
            if seo_url and "?" not in seo_url and "&" in seo_url:
                seo_url = seo_url.replace("&", "?", 1)
            # Address: locality + city
            locality = it.get("lmtDName") or it.get("locSeoName") or ""
            city = it.get("ctName") or CITY
            address = ", ".join(p for p in (locality, city) if p)
            # Geo
            lat = lng = None
            coord = it.get("ltcoordGeo") or ""
            if isinstance(coord, str) and "," in coord:
                try:
                    lat_s, lng_s = coord.split(",", 1)
                    lat = float(lat_s) or None
                    lng = float(lng_s) or None
                except ValueError:
                    pass
            # Furnishing
            furn = (it.get("furnishedD") or "unknown").lower()
            if "semi" in furn:
                furn = "semi"
            elif "unfurnished" in furn or "not furnished" in furn:
                furn = "unfurnished"
            elif "fully" in furn or "furnished" in furn:
                furn = "furnished"
            out.append(Listing(
                id=f"magicbricks_{listing_id}", source="magicbricks",
                title=str(it.get("propertyTitle") or "")[:120],
                address=address, price=price, url=seo_url,
                lat=lat, lng=lng, furnishing=furn,
            ))
        return out

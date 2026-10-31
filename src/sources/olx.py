from __future__ import annotations
import json
import re
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

# OLX server-renders results into ``window.__APP``, a JS object literal with
# unquoted top-level keys. We avoid parsing the wrapper by walking to each
# per-ad sub-object (keyed by id) which IS strict JSON.
_AD_IDS = re.compile(r'"ad_id":"(\d+)"')
_URL_MAP = re.compile(r'"url":"(/item/[^"]*iid-(\d+))"')

# A canonical ad object begins with ``"<id>":{"id":"<id>"``.
def _ad_object_re(ad_id: str) -> re.Pattern:
    e = re.escape(ad_id)
    return re.compile(rf'"{e}":\{{"id":"{e}"')


def _bracket_extract(html: str, i: int) -> str | None:
    """Return the substring starting at ``i`` (which points at ``{``) up to
    and including the matching ``}``. Handles strings + escapes."""
    if html[i] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[i : j + 1]
    return None


class OLX(SourceAdapter):
    name = "olx"
    rate = RateLimit(rate=0.5, burst=2)
    needs_browser = False

    def _urls(self, cfg) -> list[str]:
        from config import SEARCH_AREAS, MAX_RENT, PROPERTY_SLUG
        beds = PROPERTY_SLUG[0]
        return [
            f"https://www.olx.in/items/q-{beds}-bhk-rent-{a.lower().replace(' ', '-')}?filter=price_max_{MAX_RENT}"
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
                                      "Referer": "https://www.olx.in/"})
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
        # SSR-rendered ItemList carries the canonical slug per ad
        url_map: dict[str, str] = {}
        for slug, aid in _URL_MAP.findall(html):
            url_map.setdefault(aid, slug)

        ad_ids: list[str] = []
        seen_ids: set[str] = set()
        for aid in _AD_IDS.findall(html):
            if aid in seen_ids:
                continue
            seen_ids.add(aid)
            ad_ids.append(aid)

        out: list[Listing] = []
        for aid in ad_ids:
            head = _ad_object_re(aid).search(html)
            if not head:
                continue
            obj_start = head.start() + len(aid) + 3  # skip ``"<id>":``
            blob = _bracket_extract(html, obj_start)
            if not blob:
                continue
            try:
                ad = json.loads(blob)
            except json.JSONDecodeError:
                continue
            price_raw = ((ad.get("price") or {}).get("value") or {}).get("raw")
            try:
                price = int(price_raw or 0)
            except (TypeError, ValueError):
                continue
            if not (MIN_RENT <= price <= MAX_RENT):
                continue
            title = str(ad.get("title") or "")[:120]
            # Address: SUBLOCALITY + ADMIN_LEVEL_3 + ADMIN_LEVEL_1
            res = ad.get("locations_resolved") or {}
            address_parts = [
                res.get("SUBLOCALITY_LEVEL_1_name"),
                res.get("ADMIN_LEVEL_3_name") or CITY,
                res.get("ADMIN_LEVEL_1_name"),
            ]
            address = ", ".join(p for p in address_parts if p)
            # Geo
            lat = lng = None
            locs = ad.get("locations") or []
            if locs and isinstance(locs[0], dict):
                lat = locs[0].get("lat")
                lng = locs[0].get("lon")
            # Furnishing from parameters
            furn = "unknown"
            for p in ad.get("parameters") or []:
                if p.get("key") == "furnished":
                    v = (p.get("value") or "").lower()
                    if v == "no":
                        furn = "unfurnished"
                    elif v == "semi":
                        furn = "semi"
                    elif v in ("yes", "fully"):
                        furn = "furnished"
                    break
            slug = url_map.get(aid)
            url = f"https://www.olx.in{slug}" if slug else f"https://www.olx.in/item/iid-{aid}"
            out.append(Listing(
                id=f"olx_{aid}", source="olx",
                title=title, address=address, price=price, url=url,
                lat=lat, lng=lng, furnishing=furn,
            ))
        return out

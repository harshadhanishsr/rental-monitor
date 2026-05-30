from __future__ import annotations
import json
import re
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)
_SPID = re.compile(r"spid-([A-Z]\d+)")


class NinetyNineAcres(SourceAdapter):
    """99acres returns server-rendered HTML with JSON-LD blocks.

    Each listing is split across two adjacent blocks: ``Apartment`` /
    ``SingleFamilyResidence`` carries url/address/geo, ``RentAction`` carries
    price. They are joined on ``name`` (which embeds the locality and is
    unique per listing on a single search page).
    """

    name = "99acres"
    rate = RateLimit(rate=0.5, burst=2)
    needs_browser = False  # JSON-LD fast path; falls through to curl_cffi at runtime

    def _urls(self, cfg) -> list[str]:
        from config import MAX_RENT, MIN_RENT, PROPERTY_SLUG
        # 99acres uses numeric city id; 32 = Chennai. Plumbing the lookup is
        # out of scope for v2 cut — keep Chennai hard-coded until the registry
        # learns to map names to ids.
        beds = PROPERTY_SLUG[0]
        return [(
            f"https://www.99acres.com/search/property/rent/residential/chennai"
            f"?city=32&preference=R&bedroom={beds}"
            f"&budget_max={MAX_RENT}&budget_min={MIN_RENT}"
        )]

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome110") as session:
            seen_ids: set[str] = set()
            for url in self._urls(ctx.config):
                ctx.breaker.check()
                await ctx.bucket.acquire()
                try:
                    r = await session.get(
                        url, headers={"Accept-Language": "en-IN,en;q=0.9"})
                except Exception:
                    ctx.breaker.record_failure()
                    continue
                if r.status_code not in (200, 206):
                    continue
                for listing in self._parse(r.text):
                    if listing.id in seen_ids:
                        continue
                    seen_ids.add(listing.id)
                    yield listing

    def _parse(self, html: str) -> list[Listing]:
        from config import CITY, MAX_RENT, MIN_RENT
        apts: list[dict] = []
        prices: dict[str, int] = {}
        for m in _JSON_LD.finditer(html):
            try:
                data = json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                continue
            for item in (data if isinstance(data, list) else [data]):
                t = item.get("@type", "")
                if isinstance(t, list):
                    t_set = set(t)
                else:
                    t_set = {t}
                if t_set & {"Apartment", "SingleFamilyResidence",
                            "Residence", "House"}:
                    if item.get("url"):
                        apts.append(item)
                elif t == "RentAction":
                    obj_name = (item.get("object") or {}).get("name")
                    spec = item.get("priceSpecification") or {}
                    raw = spec.get("price")
                    if obj_name and raw:
                        try:
                            prices[obj_name] = int(str(raw).replace(",", ""))
                        except ValueError:
                            pass
        out: list[Listing] = []
        for item in apts:
            name = item.get("name") or ""
            price = prices.get(name)
            if not price or not (MIN_RENT <= price <= MAX_RENT):
                continue
            url = str(item.get("url") or "")
            m_id = _SPID.search(url)
            listing_id = m_id.group(1) if m_id else url[-12:]
            addr_obj = item.get("address") or {}
            if isinstance(addr_obj, dict):
                parts = [addr_obj.get("name"),
                         addr_obj.get("streetAddress"),
                         addr_obj.get("addressLocality")]
                address = ", ".join(p for p in parts if p)
            else:
                address = str(addr_obj)
            if CITY.lower() not in address.lower():
                address = f"{address}, {CITY}".strip(", ")
            geo = item.get("geo") or {}
            try:
                lat = float(geo.get("latitude") or 0) or None
                lng = float(geo.get("longitude") or 0) or None
            except (ValueError, TypeError):
                lat = lng = None
            out.append(Listing(
                id=f"99acres_{listing_id}", source="99acres",
                title=str(name)[:120],
                address=address, price=price, url=url,
                lat=lat, lng=lng,
            ))
        return out

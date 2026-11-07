"""
OLX scraper — requests-based with __PRELOADED_STATE__ / HTML parsing.
OLX India embeds listing data in a window.__PRELOADED_STATE__ JSON object.
"""
import json
import logging
import re
import time
try:
    from curl_cffi import requests as _requests
    _CFFI = True
except ImportError:
    import requests as _requests
    _CFFI = False
from src.models import Listing
from config import SEARCH_AREAS, CITY, PROPERTY_LABEL, MAX_RENT

logger = logging.getLogger(__name__)

# Build search queries from config areas
SEARCH_QUERIES = [
    (area.lower(), f"{PROPERTY_LABEL.lower()} {area.lower()} {CITY.lower()} rent")
    for area in SEARCH_AREAS
]

OLX_SEARCH_URL = "https://www.olx.in/items/q-{query}?filter=price_max_{max_rent}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.olx.in/",
    "Connection": "keep-alive",
}

_PRELOADED_RE = re.compile(
    r'window\.__PRELOADED_STATE__\s*=\s*({.*?});\s*</script>', re.DOTALL
)


def _parse_price(text: str) -> int | None:
    text = text.replace(",", "")
    m = re.search(r"\d{4,}", text)
    return int(m.group()) if m else None


def _extract_from_preloaded(html: str, area: str) -> list[Listing]:
    match = _PRELOADED_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, Exception):
        return []

    ads = None
    for path in [
        ["listing", "listingAds"],
        ["listing", "ads"],
        ["ads", "list"],
        ["search", "ads"],
    ]:
        obj = data
        try:
            for key in path:
                obj = obj[key]
            if isinstance(obj, list) and obj:
                ads = obj
                break
        except (KeyError, TypeError):
            continue

    if not ads:
        return []

    listings = []
    for ad in ads:
        try:
            ad_id = str(ad.get("ad_id") or ad.get("id") or "")
            if not ad_id:
                continue
            title = ad.get("title") or f"1 BHK, {area}"
            price_info = ad.get("price") or {}
            price = None
            if isinstance(price_info, dict):
                price = price_info.get("value") or price_info.get("amount")
            elif isinstance(price_info, (int, float)):
                price = int(price_info)
            if not price:
                price = _parse_price(str(price_info))
            if not price or price > MAX_RENT:
                continue
            loc = ad.get("location") or {}
            if isinstance(loc, dict):
                address = loc.get("name") or loc.get("city_name") or f"{area}, {CITY}"
            else:
                address = f"{area}, {CITY}"
            url = ad.get("url") or f"https://www.olx.in/item/{ad_id}"
            if not url.startswith("http"):
                url = "https://www.olx.in" + url
            images = []
            for img in (ad.get("images") or [])[:3]:
                src = img.get("url") or img.get("src") or "" if isinstance(img, dict) else img if isinstance(img, str) else ""
                if src and not src.startswith("data:"):
                    images.append(src)
            listings.append(Listing(
                id=ad_id,
                source="olx",
                title=title,
                address=address,
                price=int(price),
                url=url,
                images=images,
            ))
        except Exception:
            logger.exception("OLX: error parsing ad")
    return listings


def _extract_from_html(html: str, area: str) -> list[Listing]:
    pattern = re.compile(r'href=["\'](https://www\.olx\.in/item/[^\"\' ]+ID(\d+)\.html)["\']')
    seen: set[str] = set()
    listings = []
    for m in pattern.finditer(html):
        href, ad_id = m.group(1), m.group(2)
        if ad_id in seen:
            continue
        seen.add(ad_id)
        context = html[m.start():m.start() + 600]
        title_m = re.search(r'(?:data-aut-id=["\']itemTitle["\'][^>]*>|<h[23][^>]*>)\s*([^<]{5,80})', context)
        title = title_m.group(1).strip() if title_m else f"1 BHK, {area}"
        price_m = re.search(r"(?:₹|Rs\.?)\s*([\d,]+)", context)
        if not price_m:
            continue
        price = _parse_price(price_m.group())
        if not price or price > MAX_RENT:
            continue
        listings.append(Listing(
            id=ad_id,
            source="olx",
            title=title,
            address=f"{area}, {CITY}",
            price=price,
            url=href,
        ))
    return listings


def _scrape_area(area_key: str, query: str) -> list[Listing]:
    url = OLX_SEARCH_URL.format(
        query=query.replace(" ", "-"),
        max_rent=MAX_RENT,
    )
    try:
        if _CFFI:
            session = _requests.Session(impersonate="chrome110")
            resp = session.get(url, headers=_HEADERS, timeout=30)
        else:
            resp = _requests.get(url, headers=_HEADERS, timeout=30)
        if resp.status_code not in (200, 206):
            logger.warning("OLX [%s]: HTTP %d", area_key, resp.status_code)
            return []
        html = resp.text
        listings = _extract_from_preloaded(html, area_key)
        if listings:
            logger.info("OLX [%s]: %d listings via __PRELOADED_STATE__", area_key, len(listings))
            return listings
        listings = _extract_from_html(html, area_key)
        if listings:
            logger.info("OLX [%s]: %d listings via HTML parse", area_key, len(listings))
            return listings
        logger.info("OLX [%s]: 0 listings found", area_key)
        return []
    except Exception:
        logger.exception("OLX [%s]: request failed", area_key)
        return []


def scrape() -> list[Listing]:
    seen: set[str] = set()
    all_listings: list[Listing] = []
    for area_key, query in SEARCH_QUERIES:
        for l in _scrape_area(area_key, query):
            if l.id not in seen:
                seen.add(l.id)
                all_listings.append(l)
        time.sleep(2)
    logger.info("OLX total unique: %d", len(all_listings))
    return all_listings

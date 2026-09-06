"""
NoBroker scraper — requests-based with __NEXT_DATA__ JSON extraction.
Falls back to HTML parsing if JSON extraction fails.
"""
import json
import logging
import re
import time
try:
    from curl_cffi import requests as _cffi_requests
    _CFFI_AVAILABLE = True
except ImportError:
    import requests as _cffi_requests
    _CFFI_AVAILABLE = False
from src.models import Listing
from config import SEARCH_AREAS, CITY, PROPERTY_SLUG, MAX_RENT

logger = logging.getLogger(__name__)

# Build search URLs from config areas
def _make_urls():
    city = CITY.lower()
    urls = []
    for area in SEARCH_AREAS:
        a = area.lower().replace(" ", "-")
        urls.append(f"https://www.nobroker.in/{PROPERTY_SLUG}-flats-for-rent-in-{a}_{city}")
    return urls

SEARCH_URLS = _make_urls()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nobroker.in/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "DNT": "1",
}

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.DOTALL
)


def _parse_price(text: str) -> int | None:
    text = text.replace(",", "")
    m = re.search(r"\d{4,}", text)
    return int(m.group()) if m else None


def _extract_from_next_data(html: str, area: str) -> list[Listing]:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    prop_list = None
    for path in [
        ["props", "pageProps", "propertyList"],
        ["props", "pageProps", "data", "propertyList"],
        ["props", "pageProps", "searchResult", "propertyList"],
        ["props", "pageProps", "initialState", "properties"],
        ["props", "pageProps", "properties"],
    ]:
        obj = data
        try:
            for key in path:
                obj = obj[key]
            if isinstance(obj, list) and obj:
                prop_list = obj
                break
        except (KeyError, TypeError):
            continue

    if not prop_list:
        text = match.group(1)
        prop_matches = re.findall(r'"propertyId"\s*:\s*"?(\d+)"?', text)
        if prop_matches:
            listings = []
            rent_matches = re.findall(r'"expectedRent"\s*:\s*(\d+)', text)
            addr_matches = re.findall(r'"localityName"\s*:\s*"([^"]+)"', text)
            for i, pid in enumerate(prop_matches):
                price = int(rent_matches[i]) if i < len(rent_matches) else None
                if not price or price > MAX_RENT:
                    continue
                loc = addr_matches[i] if i < len(addr_matches) else area
                listings.append(Listing(
                    id=pid,
                    source="nobroker",
                    title=f"1 BHK, {loc}",
                    address=f"{loc}, {CITY}",
                    price=price,
                    url=f"https://www.nobroker.in/property/rental/{CITY.lower()}/{pid}",
                ))
            return listings
        return []

    listings = []
    for prop in prop_list:
        try:
            pid = str(prop.get("propertyId") or prop.get("id") or "")
            if not pid:
                continue
            rent = (
                prop.get("rentDetails", {}) or {}
            ).get("expectedRent") or prop.get("rent") or prop.get("price") or 0
            if not rent:
                continue
            price = int(rent)
            if price > MAX_RENT:
                continue
            locality = prop.get("localityName") or prop.get("locality") or area
            subloc = prop.get("subLocalityName") or ""
            address = f"{subloc}, {locality}, {CITY}" if subloc else f"{locality}, {CITY}"
            title = prop.get("title") or f"1 BHK, {locality}"
            furnishing = prop.get("furnishingDetails") or prop.get("furnishing") or "unknown"
            listings.append(Listing(
                id=pid,
                source="nobroker",
                title=title,
                address=address,
                price=price,
                url=f"https://www.nobroker.in/property/rental/{CITY.lower()}/{pid}",
                furnishing=furnishing,
            ))
        except Exception:
            logger.exception("NoBroker: error parsing JSON property")
    return listings


def _extract_from_html(html: str, area: str) -> list[Listing]:
    pattern = re.compile(r'href=["\'](/property/rental/[^"\'?]+/([^"\'?/]+))["\']')
    seen = set()
    listings = []
    for m in pattern.finditer(html):
        path, pid = m.group(1), m.group(2)
        if not pid.isdigit() or pid in seen:
            continue
        seen.add(pid)
        context = html[m.start():m.start() + 500]
        price = None
        pm = re.search(r"(?:₹|Rs\.?)\s*([\d,]+)", context)
        if pm:
            price = _parse_price(pm.group(1))
        if not price or price > MAX_RENT:
            continue
        listings.append(Listing(
            id=pid,
            source="nobroker",
            title=f"1 BHK, {area}",
            address=f"{area}, {CITY}",
            price=price,
            url=f"https://www.nobroker.in{path}",
        ))
    return listings


def _scrape_url(url: str) -> list[Listing]:
    area = url.split("in-")[1].split("_")[0] if "in-" in url else CITY.lower()
    try:
        if _CFFI_AVAILABLE:
            session = _cffi_requests.Session(impersonate="chrome110")
            resp = session.get(url, headers=_HEADERS, timeout=30)
        else:
            import requests as _req
            session = _req.Session()
            resp = session.get(url, headers=_HEADERS, timeout=30)
        html = resp.text
        listings = _extract_from_next_data(html, area)
        if not listings:
            listings = _extract_from_html(html, area)
        logger.info("NoBroker [%s]: found %d listings", area, len(listings))
        return listings
    except Exception:
        logger.exception("NoBroker [%s]: request failed", area)
        return []


def scrape() -> list[Listing]:
    seen: set[str] = set()
    all_listings: list[Listing] = []
    for url in SEARCH_URLS:
        for l in _scrape_url(url):
            if l.id not in seen:
                seen.add(l.id)
                all_listings.append(l)
        time.sleep(2)
    logger.info("NoBroker total unique: %d", len(all_listings))
    return all_listings

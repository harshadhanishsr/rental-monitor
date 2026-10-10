"""
MagicBricks scraper — requests-based with JSON extraction.
Tries __NEXT_DATA__ or window.__INITIAL_STATE__ JSON, then falls back to HTML parsing.
"""
import json
import logging
import re
import time
import requests
from src.models import Listing

logger = logging.getLogger(__name__)

SEARCH_AREAS = [
    ("Chromepet", "CHENN4320"),
    ("Pallavaram", "CHENN4330"),
    ("Tambaram", "CHENN4340"),
    ("Nanganallur", "CHENN4350"),
]

# MagicBricks JSON search API (discovered via network inspection)
MB_API_URL = "https://www.magicbricks.com/mbsrp/propertySearch.html"
MB_PAGE_URL = (
    "https://www.magicbricks.com/property-for-rent/residential-rent/"
    "flats-in-{area}/mc=Chennai?bedroom=1BHK&maxBudget=15000"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.magicbricks.com/",
    "Connection": "keep-alive",
}

_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.magicbricks.com/",
    "X-Requested-With": "XMLHttpRequest",
}

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.DOTALL
)
_INITIAL_STATE_RE = re.compile(
    r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*(?:</script>|window\.)', re.DOTALL
)
_PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR)?\s*([\d,]+)\s*(?:/month|pm|per month)?", re.IGNORECASE)


def _parse_price(text: str) -> int | None:
    text = str(text).replace(",", "")
    m = re.search(r"\d{4,}", text)
    return int(m.group()) if m else None


def _try_api(area: str, area_id: str) -> list[Listing]:
    """Try MagicBricks JSON search API."""
    params = {
        "editSearch": "Y",
        "category": "S",
        "proptype": "flats",
        "bedroom": "1BHK",
        "city": "Chennai",
        "locality": area,
        "localityIds": area_id,
        "rentBudgetMin": "0",
        "rentBudgetMax": "15000",
        "offset": "0",
        "pageSize": "30",
    }
    try:
        resp = requests.get(MB_API_URL, params=params, headers=_API_HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    props = None
    for path in [["resultList"], ["propertyList"], ["data", "propertyList"]]:
        obj = data
        try:
            for key in path:
                obj = obj[key]
            if isinstance(obj, list) and obj:
                props = obj
                break
        except (KeyError, TypeError):
            pass

    if not props:
        return []

    listings = []
    for prop in props:
        try:
            pid = str(prop.get("propId") or prop.get("id") or "")
            if not pid:
                continue
            price = prop.get("priceDisplay") or prop.get("price") or prop.get("rent") or 0
            if isinstance(price, str):
                price = _parse_price(price) or 0
            price = int(price)
            if not price or price > 20000:
                continue

            title = prop.get("heading") or prop.get("title") or f"1 BHK, {area}"
            locality = prop.get("localityTitle") or prop.get("locality") or area
            address = f"{locality}, Chennai"
            url = prop.get("propUrl") or f"https://www.magicbricks.com/propertyDetails/{pid}.html"
            if not url.startswith("http"):
                url = "https://www.magicbricks.com" + url

            listings.append(Listing(
                id=f"mb_{pid}",
                source="magicbricks",
                title=title,
                address=address,
                price=price,
                url=url,
            ))
        except Exception:
            logger.exception("MagicBricks API: error parsing property")
    return listings


def _try_page_scrape(area: str) -> list[Listing]:
    """Fetch the search page and extract JSON or HTML data."""
    url = MB_PAGE_URL.format(area=area)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        if resp.status_code not in (200, 206):
            return []
        html = resp.text

        # Try __NEXT_DATA__
        m = _NEXT_DATA_RE.search(html)
        if m:
            try:
                data = json.loads(m.group(1))
                props = None
                for path in [
                    ["props", "pageProps", "propertyList"],
                    ["props", "pageProps", "data", "propertyList"],
                    ["props", "pageProps", "initialState", "propertyList"],
                ]:
                    obj = data
                    try:
                        for key in path:
                            obj = obj[key]
                        if isinstance(obj, list) and obj:
                            props = obj
                            break
                    except (KeyError, TypeError):
                        pass

                if props:
                    listings = []
                    for prop in props:
                        try:
                            pid = str(prop.get("propId") or prop.get("id") or "")
                            if not pid:
                                continue
                            price = prop.get("price") or prop.get("rent") or 0
                            if isinstance(price, str):
                                price = _parse_price(price) or 0
                            price = int(price)
                            if not price or price > 20000:
                                continue
                            locality = prop.get("localityTitle") or prop.get("locality") or area
                            url_prop = f"https://www.magicbricks.com/propertyDetails/{pid}.html"
                            listings.append(Listing(
                                id=f"mb_{pid}",
                                source="magicbricks",
                                title=prop.get("heading") or f"1 BHK, {locality}",
                                address=f"{locality}, Chennai",
                                price=price,
                                url=url_prop,
                            ))
                        except Exception:
                            pass
                    if listings:
                        return listings
            except Exception:
                pass

        # Try HTML card scraping
        # MagicBricks property cards have data-id attribute
        card_pattern = re.compile(
            r'data-propid=["\'](\d+)["\'].*?'
            r'(?:₹|Rs\.?)\s*([\d,]+)',
            re.DOTALL,
        )
        seen: set[str] = set()
        listings = []
        for m in card_pattern.finditer(html):
            pid, price_raw = m.group(1), m.group(2)
            if pid in seen:
                continue
            seen.add(pid)
            price = _parse_price(price_raw)
            if not price or price > 20000:
                continue

            # Get context to extract title/locality
            ctx_start = max(0, m.start() - 200)
            context = html[ctx_start:m.start() + 600]
            title_m = re.search(r'(?:class=["\'][^"\']*(?:title|heading)[^"\']*["\'][^>]*>|<h[1-4][^>]*>)\s*([^<]{10,100})', context)
            title = title_m.group(1).strip() if title_m else f"1 BHK, {area}"

            listings.append(Listing(
                id=f"mb_{pid}",
                source="magicbricks",
                title=title,
                address=f"{area}, Chennai",
                price=price,
                url=f"https://www.magicbricks.com/propertyDetails/{pid}.html",
            ))
        return listings
    except Exception:
        logger.exception("MagicBricks page scrape [%s]: failed", area)
        return []


def _scrape_area(area: str, area_id: str) -> list[Listing]:
    # Try API first, then page scrape
    listings = _try_api(area, area_id)
    if not listings:
        listings = _try_page_scrape(area)
    logger.info("MagicBricks [%s]: found %d listings", area, len(listings))
    return listings


def scrape() -> list[Listing]:
    seen: set[str] = set()
    all_listings: list[Listing] = []
    for area, area_id in SEARCH_AREAS:
        for l in _scrape_area(area, area_id):
            if l.id not in seen:
                seen.add(l.id)
                all_listings.append(l)
        time.sleep(2)
    logger.info("MagicBricks total unique: %d", len(all_listings))
    return all_listings

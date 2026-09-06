"""
Sulekha Property scraper — JSON-LD extraction.
Sulekha embeds structured listing data in schema.org JSON-LD on every search page.
Uses curl_cffi for Chrome impersonation (required to get the data).
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
from config import SEARCH_AREAS, CITY, PROPERTY_SLUG, MAX_RENT, MIN_RENT

logger = logging.getLogger(__name__)

# Build Sulekha search URLs from config areas
def _make_urls():
    city = CITY.lower()
    urls = []
    beds = PROPERTY_SLUG[0]  # "1", "2", etc.
    for area in SEARCH_AREAS:
        a = area.lower().replace(" ", "-")
        urls.append(
            f"https://property.sulekha.com/{beds}-bhk-apartments-flats-for-rent/{city}/{a}"
        )
    for area in SEARCH_AREAS[:3]:
        a = area.lower().replace(" ", "-")
        urls.append(
            f"https://property.sulekha.com/{beds}-bhk-individual-houses-villas-for-rent/{city}/{a}"
        )
    # City-wide fallback
    urls.append(f"https://property.sulekha.com/{beds}-bhk-apartments-flats-for-rent/{city}")
    return urls

SEARCH_URLS = _make_urls()

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://property.sulekha.com/",
}

_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)
_PRICE_RE = re.compile(r"(?:Rent|rent|₹|Rs\.?|INR)[^₹\d]{0,15}([\d,]{4,6})")
_ID_RE = re.compile(r"-(\d{6,})-ad$")


def _parse_price(text: str) -> int | None:
    text = str(text)
    m = _PRICE_RE.search(text)
    if m:
        digits = m.group(1).replace(",", "")
        try:
            v = int(digits)
            if MIN_RENT <= v <= MAX_RENT:
                return v
        except ValueError:
            pass
    return None


def _extract_from_json_ld(html: str, area: str) -> list[Listing]:
    listings = []
    for m in _JSON_LD_RE.finditer(html):
        try:
            raw = m.group(1).strip()
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            try:
                item_types = item.get("@type", [])
                if isinstance(item_types, str):
                    item_types = [item_types]
                if not any(t in item_types for t in ["Apartment", "Product", "House", "SingleFamilyResidence"]):
                    continue

                url = item.get("url", "")
                if not url or "sulekha" not in url:
                    continue

                id_m = _ID_RE.search(url)
                listing_id = id_m.group(1) if id_m else url[-12:]
                title = item.get("name", f"1 BHK, {area}")

                desc = item.get("description", "")
                offers = item.get("offers", {})
                offers_price = None
                if isinstance(offers, dict):
                    offers_price = offers.get("price") or offers.get("lowPrice")
                elif isinstance(offers, list) and offers:
                    offers_price = offers[0].get("price")

                price = None
                if offers_price:
                    try:
                        price = int(str(offers_price).replace(",", ""))
                        if not (MIN_RENT <= price <= MAX_RENT):
                            price = None
                    except ValueError:
                        pass

                if not price:
                    price = _parse_price(desc)
                if not price:
                    price = _parse_price(title)
                if not price:
                    continue

                address = item.get("address", area)
                geo = item.get("geo", {})
                lat = lng = None
                try:
                    lat_v = float(geo.get("latitude", 0))
                    lng_v = float(geo.get("longitude", 0))
                    if lat_v and lng_v and lat_v != 0.0:
                        lat, lng = lat_v, lng_v
                except (ValueError, TypeError):
                    pass

                if CITY.lower() not in address.lower():
                    address = f"{address}, {CITY}"

                images = []
                img = item.get("image")
                if isinstance(img, str):
                    images = [img]
                elif isinstance(img, list):
                    images = [i for i in img if isinstance(i, str)][:3]

                listings.append(Listing(
                    id=f"sulekha_{listing_id}",
                    source="sulekha",
                    title=title[:120],
                    address=address,
                    price=price,
                    url=url,
                    images=images,
                    lat=lat,
                    lng=lng,
                ))
            except Exception:
                logger.exception("Sulekha: error parsing JSON-LD item")
    return listings


def _scrape_url(url: str) -> list[Listing]:
    area = url.rstrip("/").split("/")[-1].replace("-", " ").title()
    try:
        if _CFFI:
            session = _requests.Session(impersonate="chrome110")
            resp = session.get(url, headers=_HEADERS, timeout=30)
        else:
            resp = _requests.get(url, headers=_HEADERS, timeout=30)
        if resp.status_code not in (200, 206):
            logger.warning("Sulekha [%s]: HTTP %d", area, resp.status_code)
            return []
        listings = _extract_from_json_ld(resp.text, area)
        logger.info("Sulekha [%s]: found %d listings via JSON-LD", area, len(listings))
        return listings
    except Exception:
        logger.exception("Sulekha [%s]: request failed", area)
        return []


def scrape() -> list[Listing]:
    seen: set[str] = set()
    all_listings: list[Listing] = []
    for url in SEARCH_URLS:
        for l in _scrape_url(url):
            if l.id not in seen:
                seen.add(l.id)
                all_listings.append(l)
        time.sleep(1.5)
    logger.info("Sulekha total unique: %d", len(all_listings))
    return all_listings

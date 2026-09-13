"""
Housing.com scraper — requests-based with __NEXT_DATA__ JSON extraction.
Housing.com (PropTiger group) uses Next.js SSR, so data is embedded in HTML.
"""
import json
import logging
import re
import time
import requests
from src.models import Listing

logger = logging.getLogger(__name__)

# Housing.com search URLs for Chennai near Chromepet
SEARCH_AREAS = [
    ("chromepet", "https://housing.com/in/rent/1-bhk-flats-apartments-in-chromepet-chennai-mdgf9qmvt0z5"),
    ("pallavaram", "https://housing.com/in/rent/1-bhk-flats-apartments-in-pallavaram-chennai-mlhfd5vhulb4"),
    ("tambaram", "https://housing.com/in/rent/1-bhk-flats-apartments-in-tambaram-chennai-mls7c0fhuh3m"),
    ("nanganallur", "https://housing.com/in/rent/1-bhk-flats-apartments-in-nanganallur-chennai"),
    # Generic fallback
    ("chennai_south", "https://housing.com/in/rent/1-bhk-flats-apartments-in-chromepet-chennai?budget=0-15000"),
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://housing.com/",
    "Connection": "keep-alive",
}

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.DOTALL
)


def _parse_price(text: str) -> int | None:
    text = str(text).replace(",", "")
    m = re.search(r"\d{4,}", text)
    return int(m.group()) if m else None


def _extract_listings_from_data(data: dict, area: str) -> list[Listing]:
    """Navigate Housing.com's __NEXT_DATA__ structure to find listings."""
    # Try multiple known paths in Housing.com's JSON
    props_list = None
    for path in [
        ["props", "pageProps", "listings"],
        ["props", "pageProps", "data", "listings"],
        ["props", "pageProps", "searchResult", "listings"],
        ["props", "pageProps", "initialData", "listings"],
        ["props", "pageProps", "serverSideProps", "listings"],
    ]:
        obj = data
        try:
            for key in path:
                obj = obj[key]
            if isinstance(obj, list) and obj:
                props_list = obj
                break
        except (KeyError, TypeError):
            pass

    if not props_list:
        # Try to find by searching for price keys
        text = json.dumps(data)
        id_matches = re.findall(r'"listing_id"\s*:\s*"?([A-Za-z0-9_-]+)"?', text)
        if id_matches:
            price_matches = re.findall(r'"expectedPrice"\s*:\s*(\d+)', text)
            locality_matches = re.findall(r'"localityName"\s*:\s*"([^"]+)"', text)
            listings = []
            for i, lid in enumerate(id_matches[:20]):
                price = int(price_matches[i]) if i < len(price_matches) else None
                if not price or price > 20000:
                    continue
                loc = locality_matches[i] if i < len(locality_matches) else area
                listings.append(Listing(
                    id=f"housing_{lid}",
                    source="housing",
                    title=f"1 BHK, {loc}",
                    address=f"{loc}, Chennai",
                    price=price,
                    url=f"https://housing.com/in/rent/listing/{lid}",
                ))
            return listings
        return []

    listings = []
    for prop in props_list:
        try:
            # Handle nested structure
            if "listing" in prop:
                prop = prop["listing"]

            lid = str(
                prop.get("id") or prop.get("listing_id") or
                prop.get("propertyId") or prop.get("projectId") or ""
            )
            if not lid:
                continue

            price = (
                prop.get("price") or prop.get("expectedPrice") or
                prop.get("rent") or prop.get("rentAmount") or 0
            )
            if isinstance(price, str):
                price = _parse_price(price) or 0
            price = int(price)
            if not price or price > 20000:
                continue

            locality = (
                prop.get("locality", {}) if isinstance(prop.get("locality"), dict)
                else {"name": prop.get("locality") or area}
            )
            loc_name = locality.get("name") or area
            address = f"{loc_name}, Chennai"
            title = prop.get("name") or prop.get("title") or f"1 BHK, {loc_name}"
            prop_url = prop.get("url") or f"https://housing.com/in/rent/listing/{lid}"
            if not prop_url.startswith("http"):
                prop_url = "https://housing.com" + prop_url

            furnishing = prop.get("furnishingStatus") or prop.get("furnishing") or "unknown"

            listings.append(Listing(
                id=f"housing_{lid}",
                source="housing",
                title=title,
                address=address,
                price=price,
                url=prop_url,
                furnishing=furnishing,
            ))
        except Exception:
            logger.exception("Housing.com: error parsing listing")
    return listings


def _scrape_area(area: str, url: str) -> list[Listing]:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        if resp.status_code not in (200, 206):
            logger.warning("Housing.com [%s]: HTTP %d", area, resp.status_code)
            return []
        html = resp.text

        m = _NEXT_DATA_RE.search(html)
        if m:
            try:
                data = json.loads(m.group(1))
                listings = _extract_listings_from_data(data, area)
                if listings:
                    logger.info("Housing.com [%s]: %d listings via __NEXT_DATA__", area, len(listings))
                    return listings
            except Exception:
                logger.exception("Housing.com [%s]: JSON parse error", area)

        # HTML fallback — look for price + link patterns
        seen: set[str] = set()
        listings = []
        link_price_re = re.compile(
            r'href=["\'](https://housing\.com/in/rent/[^"\']+)["\']'
            r'.*?(?:₹|Rs\.?)\s*([\d,]+)',
            re.DOTALL,
        )
        for lm in link_price_re.finditer(html[:50000]):
            href = lm.group(1)
            hid = re.sub(r"[^a-zA-Z0-9]", "", href)[-12:]
            if hid in seen:
                continue
            seen.add(hid)
            price = _parse_price(lm.group(2))
            if not price or price > 20000:
                continue
            listings.append(Listing(
                id=f"housing_{hid}",
                source="housing",
                title=f"1 BHK, {area.replace('_', ' ').title()}",
                address=f"{area.replace('_', ' ').title()}, Chennai",
                price=price,
                url=href,
            ))

        logger.info("Housing.com [%s]: %d listings via HTML", area, len(listings))
        return listings
    except Exception:
        logger.exception("Housing.com [%s]: request failed", area)
        return []


def scrape() -> list[Listing]:
    seen: set[str] = set()
    all_listings: list[Listing] = []
    for area, url in SEARCH_AREAS:
        for l in _scrape_area(area, url):
            if l.id not in seen:
                seen.add(l.id)
                all_listings.append(l)
        time.sleep(2)
    logger.info("Housing.com total unique: %d", len(all_listings))
    return all_listings

"""
Quikr scraper — requests-based HTML parsing.
Quikr.com Chennai rental listings via HTTP requests (no browser needed).
"""
import hashlib
import json
import logging
import re
import time
import requests
from src.models import Listing

logger = logging.getLogger(__name__)

SEARCH_URLS = [
    "https://www.quikr.com/homes/flats-for-rent-in-Chromepet+Chennai/ci10/cni175/sb1/bd1/p15000",
    "https://www.quikr.com/homes/flats-for-rent-in-Pallavaram+Chennai/ci10/cni175/sb1/bd1/p15000",
    "https://www.quikr.com/homes/flats-for-rent-in-Tambaram+Chennai/ci10/cni175/sb1/bd1/p15000",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.quikr.com/",
    "Connection": "keep-alive",
}

_ID_RE = re.compile(r"(\d{7,})")
_PRICE_RE = re.compile(r"(?:₹|Rs\.?)\s*([\d,]+)")


def _parse_price(text: str) -> int | None:
    text = str(text).replace(",", "")
    m = re.search(r"\d{4,}", text)
    return int(m.group()) if m else None


def _scrape_url(url: str) -> list[Listing]:
    area = re.search(r"in-([^+/]+)", url)
    area_name = area.group(1).replace("+", " ") if area else "Chennai"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=25)
        if resp.status_code != 200:
            logger.info("Quikr [%s]: HTTP %d", area_name, resp.status_code)
            return []
        html = resp.text

        # Try JSON embedded state
        json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                ads = None
                for path in [["listing", "ads"], ["ads"], ["search", "results"]]:
                    obj = data
                    try:
                        for key in path:
                            obj = obj[key]
                        if isinstance(obj, list) and obj:
                            ads = obj
                            break
                    except (KeyError, TypeError):
                        pass
                if ads:
                    listings = []
                    for ad in ads:
                        try:
                            aid = str(ad.get("id") or "")
                            if not aid:
                                continue
                            price_raw = ad.get("price") or ad.get("rent") or 0
                            if isinstance(price_raw, str):
                                price = _parse_price(price_raw) or 0
                            else:
                                price = int(price_raw)
                            if not price or price > 20000:
                                continue
                            title = ad.get("title") or f"1 BHK, {area_name}"
                            address = (
                                (ad.get("location") or {}).get("locality") or
                                f"{area_name}, Chennai"
                            )
                            ad_url = ad.get("url") or f"https://www.quikr.com/homes/{aid}"
                            if not ad_url.startswith("http"):
                                ad_url = "https://www.quikr.com" + ad_url
                            listings.append(Listing(
                                id=f"quikr_{aid}",
                                source="quikr",
                                title=title,
                                address=address,
                                price=price,
                                url=ad_url,
                            ))
                        except Exception:
                            pass
                    if listings:
                        logger.info("Quikr [%s]: %d listings via JSON", area_name, len(listings))
                        return listings
            except Exception:
                pass

        # HTML fallback
        seen: set[str] = set()
        listings = []
        link_re = re.compile(r'href=["\'](https://www\.quikr\.com/homes/[^"\']+/(\d{7,}))["\']')
        for m in link_re.finditer(html):
            href, aid = m.group(1), m.group(2)
            if aid in seen:
                continue
            seen.add(aid)
            ctx = html[m.start():m.start() + 500]
            pm = _PRICE_RE.search(ctx)
            if not pm:
                continue
            price = _parse_price(pm.group(1))
            if not price or price > 20000:
                continue
            listings.append(Listing(
                id=f"quikr_{aid}",
                source="quikr",
                title=f"1 BHK, {area_name}",
                address=f"{area_name}, Chennai",
                price=price,
                url=href,
            ))

        logger.info("Quikr [%s]: %d listings", area_name, len(listings))
        return listings
    except Exception:
        logger.exception("Quikr [%s]: request failed", area_name)
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
    logger.info("Quikr total unique: %d", len(all_listings))
    return all_listings

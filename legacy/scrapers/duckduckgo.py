"""
DuckDuckGo meta-search scraper — "Autoresearch" approach.

Searches DuckDuckGo for rental listings across all major portals simultaneously,
bypassing their individual bot-detection systems. Extracts listing info from
search result titles and snippets.

This complements direct scrapers — catches individual NoBroker/OLX listing pages
that Playwright-based scrapers miss due to bot blocking.
"""
import hashlib
import logging
import re
import time
import requests
try:
    from curl_cffi import requests as _cffi_requests
    _CFFI_AVAILABLE = True
except ImportError:
    _cffi_requests = None
    _CFFI_AVAILABLE = False
from src.models import Listing
from config import SEARCH_AREAS, CITY, PROPERTY_LABEL, MAX_RENT, MIN_RENT

logger = logging.getLogger(__name__)

# Build search queries from config
def _make_queries():
    label = PROPERTY_LABEL.lower()  # "1 bhk"
    city  = CITY.lower()
    queries = []
    # General queries per area
    for area in SEARCH_AREAS:
        queries.append(f"{label} rent {area.lower()} {city} under {MAX_RENT}")
    # Site-specific NoBroker individual listing queries (these return property pages with price in URL)
    for area in SEARCH_AREAS[:4]:
        queries.append(f"{label} apartment for rent in {area.lower()} {city} site:nobroker.in")
    # Site-specific OLX queries
    for area in SEARCH_AREAS[:2]:
        queries.append(f"{label} flat rent {area.lower()} site:olx.in")
    return queries

SEARCH_QUERIES = _make_queries()

DDG_URL = "https://html.duckduckgo.com/html/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://duckduckgo.com/",
}

# URL patterns for INDIVIDUAL listing pages only (not portal search pages)
_LISTING_URL_PATTERNS = [
    re.compile(r"nobroker\.in/property/"),
    re.compile(r"olx\.in/item/"),
    re.compile(r"magicbricks\.com/property-details/"),
    re.compile(r"housing\.com/(?:listing|property)/"),
    re.compile(r"99acres\.com/.+-\d{7,}"),
    re.compile(r"sulekha\.com/.*-\d{6,}-ad"),
    re.compile(r"quikr\.com/homes/\w+-\d{5,}"),
]

# NoBroker encodes price in individual listing URLs: /property/...-for-rs-12000/...
_NB_PRICE_IN_URL_RE = re.compile(r"-for-rs-(\d{4,5})(?:/|-)")

# Strip search-filter phrases before price matching
_PRICE_FILTER_RE = re.compile(
    r"(?:under|below|upto|up to|max(?:imum)?)\s*(?:₹|Rs\.?)?\s*[\d,]+",
    re.IGNORECASE,
)
_PRICE_RE  = re.compile(r"(?:₹|Rs\.?)\s*([\d,]{4,6})(?!\s*(?:lakh|lac|cr|crore))", re.IGNORECASE)
_PRICE_RE2 = re.compile(r"([\d,]{4,6})\s*(?:/month|per month| pm|/mo)\b", re.IGNORECASE)

_DDG_RESULT_RE = re.compile(
    r'class="result__a"[^>]+href="//duckduckgo\.com/l/\?uddg=([^"&]+)[^"]*"[^>]*>([^<]+)</a>'
    r'(.*?)(?:class="result__snippet"[^>]*>(.*?)</(?:a|div)>)?',
    re.DOTALL,
)
_DDG_REAL_URL_RE = re.compile(r"uddg=([^&\"]+)")

_SOURCE_MAP = {
    "nobroker.in":    "nobroker",
    "magicbricks.com":"magicbricks",
    "olx.in":         "olx",
    "housing.com":    "housing",
    "99acres.com":    "99acres",
    "sulekha.com":    "sulekha",
    "quikr.com":      "quikr",
}


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_price(text: str, url: str = "") -> int | None:
    # NoBroker individual listing: price is in the URL (most reliable)
    if url and "nobroker.in/property/" in url:
        m = _NB_PRICE_IN_URL_RE.search(url)
        if m:
            v = int(m.group(1))
            if MIN_RENT <= v <= MAX_RENT:
                return v
    # Strip search-filter phrases ("under ₹15000", "below ₹12000") before matching
    clean = _PRICE_FILTER_RE.sub("", text)
    for pattern in [_PRICE_RE, _PRICE_RE2]:
        m = pattern.search(clean)
        if m:
            digits = m.group(1).replace(",", "")
            try:
                v = int(digits)
                if MIN_RENT <= v <= MAX_RENT:
                    return v
            except ValueError:
                pass
    return None


def _get_source(url: str) -> str:
    for domain, source in _SOURCE_MAP.items():
        if domain in url:
            return source
    return "web"


def _is_listing_url(url: str) -> bool:
    return any(p.search(url) for p in _LISTING_URL_PATTERNS)


def _extract_area(text: str) -> str:
    for area in SEARCH_AREAS + [
        "St Thomas Mount", "Meenambakkam", "Alandur",
        "Perungalathur", "Mudichur", "Ullagaram", "Medavakkam",
    ]:
        if area.lower() in text.lower():
            return area
    return CITY


def _search_ddg(query: str) -> list[Listing]:
    listings = []
    try:
        if _CFFI_AVAILABLE:
            session = _cffi_requests.Session(impersonate="chrome110")
            resp = session.get(
                DDG_URL,
                params={"q": query, "kl": "in-en"},
                headers=_HEADERS,
                timeout=20,
            )
        else:
            resp = requests.get(
                DDG_URL,
                params={"q": query, "kl": "in-en"},
                headers=_HEADERS,
                timeout=20,
            )
        html = resp.text

        import urllib.parse as _urlparse
        seen_urls: set[str] = set()

        for m in _DDG_RESULT_RE.finditer(html):
            try:
                url_encoded = m.group(1)
                title_raw   = m.group(2)
                snippet_raw = m.group(4) or ""
                real_url    = _urlparse.unquote(url_encoded)
                if real_url in seen_urls:
                    continue
                seen_urls.add(real_url)

                source = _get_source(real_url)
                if source == "web":
                    continue

                # Only individual listing pages
                if not _is_listing_url(real_url):
                    continue

                title   = _strip_html_tags(title_raw).strip()
                snippet = _strip_html_tags(snippet_raw).strip()
                combined = f"{title} {snippet}"

                price = _parse_price(combined, real_url)
                if not price:
                    continue  # Skip if no verifiable price

                area    = _extract_area(combined)
                address = f"{area}, {CITY}"
                pid     = hashlib.md5(real_url.encode()).hexdigest()[:12]

                listings.append(Listing(
                    id=f"ddg_{source}_{pid}",
                    source=source,
                    title=title[:120] if title else f"1 BHK, {area}",
                    address=address,
                    price=price,
                    url=real_url,
                ))
            except Exception:
                logger.exception("DDG: error parsing result")

        logger.info("DuckDuckGo [%r]: found %d listing results", query[:40], len(listings))
    except Exception:
        logger.exception("DuckDuckGo search failed for query: %r", query[:40])
    return listings


def scrape() -> list[Listing]:
    seen: set[str] = set()
    all_listings: list[Listing] = []
    for query in SEARCH_QUERIES:
        for l in _search_ddg(query):
            url_key = hashlib.md5(l.url.encode()).hexdigest()
            if url_key not in seen:
                seen.add(url_key)
                all_listings.append(l)
        time.sleep(2)
    logger.info("DuckDuckGo total unique: %d", len(all_listings))
    return all_listings

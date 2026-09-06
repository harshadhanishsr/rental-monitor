import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context, new_stealth_page

# 99acres appends zone labels that break geocoding — strip them
_ZONE_SUFFIX = re.compile(
    r",?\s*(Chennai\s*(South|North|Central|East|West|Suburbs))$",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)

# 99acres: 1 BHK RENT in Chennai (city=32), city-wide, budget ≤15000/month
SEARCH_URL = (
    "https://www.99acres.com/search/property/rent/residential/chennai"
    "?city=32&preference=R&bedroom=1&budget_max=15000"
)

# Extract ID from URL slug: "spid-S89596506" → "S89596506"
_SPID_PATTERN = re.compile(r"spid-([A-Z]\d+)", re.IGNORECASE)


def extract_id(url: str) -> str:
    match = _SPID_PATTERN.search(url)
    return match.group(1) if match else url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    """Parse price text like '₹20,000 /month' or '₹12.5K'."""
    text = text.strip().replace(",", "")
    k_match = re.search(r"(\d+\.?\d*)\s*[kK]", text)
    if k_match:
        return int(float(k_match.group(1)) * 1000)
    digits = re.sub(r"[^\d]", "", text.split("/")[0])  # only before "/"
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await new_stealth_page(ctx)
        try:
            await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=90000)
            try:
                await page.wait_for_selector(
                    "[class*='tupleNew__tupleWrap']",
                    timeout=15000,
                )
            except Exception:
                await page.wait_for_timeout(5000)

            cards = await page.query_selector_all("[class*='tupleNew__tupleWrap']")
            logger.info(f"99acres: found {len(cards)} cards")

            for card in cards:
                try:
                    # URL — the property heading anchor
                    url_el = await card.query_selector("a[class*='tupleNew__propertyHeading']")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href") or ""
                    if not url.startswith("http"):
                        url = "https://www.99acres.com" + url
                    listing_id = extract_id(url)

                    # Title — from the anchor's title attribute or h2 text
                    title = await url_el.get_attribute("title") or ""
                    if not title:
                        h2 = await card.query_selector("h2")
                        title = (await h2.inner_text()).strip() if h2 else "1 BHK"

                    # Price — first span inside priceValWrap contains "₹20,000"
                    price_el = await card.query_selector(".tupleNew__priceValWrap")
                    if not price_el:
                        continue
                    price_text = await price_el.inner_text()
                    price = parse_price(price_text)
                    if price is None:
                        continue

                    # Address — locality name or fallback to title location
                    addr_el = await card.query_selector(".tupleNew__locationName")
                    if addr_el:
                        address = (await addr_el.inner_text()).strip()
                    else:
                        # Extract "in Purasaiwakkam, Chennai" from title
                        m = re.search(r"\bin\s+(.+)$", title, re.IGNORECASE)
                        address = m.group(1).strip() if m else "Chennai"
                    # Strip 99acres zone labels ("Chennai South" etc.) before geocoding
                    address = _ZONE_SUFFIX.sub("", address).strip().strip(",").strip()
                    if "chennai" not in address.lower():
                        address += ", Chennai"

                    # Images — only real property images from imagecdn
                    img_els = await card.query_selector_all("img[src*='imagecdn.99acres.com']")
                    images = [
                        src for img in img_els[:3]
                        if (src := await img.get_attribute("src"))
                    ]

                    listings.append(Listing(
                        id=listing_id,
                        source="99acres",
                        title=title,
                        address=address,
                        price=price,
                        url=url,
                        images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing 99acres card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())

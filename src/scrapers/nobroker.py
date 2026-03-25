import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context, new_stealth_page

logger = logging.getLogger(__name__)

# Search multiple areas near the Chromepet office (each is a known working URL)
SEARCH_URLS = [
    "https://www.nobroker.in/property/rental/chennai/Chromepet?bedroom=1&budget=15000",
    "https://www.nobroker.in/property/rental/chennai/Pallavaram?bedroom=1&budget=15000",
    "https://www.nobroker.in/property/rental/chennai/Tambaram?bedroom=1&budget=15000",
    "https://www.nobroker.in/property/rental/chennai/Nanganallur?bedroom=1&budget=15000",
    "https://www.nobroker.in/property/rental/chennai/Pammal?bedroom=1&budget=15000",
    "https://www.nobroker.in/property/rental/chennai/St-Thomas-Mount?bedroom=1&budget=15000",
]

CARD_SELECTOR = (
    ".srpPropertyCard, [data-testid='property-card'], .property-tile, "
    "[class*='PropertyTile'], [class*='property-card']"
)


def extract_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_url(ctx, url: str) -> list[Listing]:
    listings = []
    page = await new_stealth_page(ctx)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector(CARD_SELECTOR, timeout=15000)
        except Exception:
            await page.wait_for_timeout(5000)

        cards = await page.query_selector_all(CARD_SELECTOR)
        logger.info("NoBroker [%s]: found %d cards", url.split("/")[-1].split("?")[0], len(cards))

        for card in cards:
            try:
                url_el = await card.query_selector("a[href*='/property/']")
                if not url_el:
                    continue
                href = await url_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = "https://www.nobroker.in" + href
                listing_id = extract_id(href)

                title_el = await card.query_selector(
                    ".property-title, h3, h4, [class*='title']"
                )
                title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                price_el = await card.query_selector(
                    ".price, [data-testid='price'], [class*='price'], "
                    "[class*='Price'], [class*='rent']"
                )
                price_text = (await price_el.inner_text()).strip() if price_el else ""
                price = parse_price(price_text)
                if price is None:
                    continue

                addr_el = await card.query_selector(
                    ".location, [data-testid='location'], [class*='location'], "
                    "[class*='address'], [class*='locality']"
                )
                address = (
                    (await addr_el.inner_text()).strip() if addr_el else "Chennai"
                )

                img_els = await card.query_selector_all("img[src]")
                images = []
                for img in img_els[:3]:
                    src = await img.get_attribute("src")
                    if src and not src.startswith("data:"):
                        images.append(src)

                listings.append(Listing(
                    id=listing_id,
                    source="nobroker",
                    title=title,
                    address=address,
                    price=price,
                    url=href,
                    images=images,
                ))
            except Exception:
                logger.exception("Error parsing NoBroker card")
    finally:
        await page.close()
    return listings


async def _scrape_async() -> list[Listing]:
    seen_ids: set[str] = set()
    all_listings: list[Listing] = []
    async with get_browser_context() as ctx:
        for url in SEARCH_URLS:
            try:
                results = await _scrape_url(ctx, url)
                for l in results:
                    if l.id not in seen_ids:
                        seen_ids.add(l.id)
                        all_listings.append(l)
            except Exception:
                logger.exception("NoBroker failed for URL: %s", url)
    logger.info("NoBroker total unique: %d", len(all_listings))
    return all_listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())

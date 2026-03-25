import asyncio
import logging
import re
from urllib.parse import urlparse, parse_qs
from src.models import Listing
from src.scrapers.base import get_browser_context, new_stealth_page

logger = logging.getLogger(__name__)

# MagicBricks: multiple areas near Chromepet office
SEARCH_URLS = [
    "https://www.magicbricks.com/property-for-rent/residential-rent/flats-in-Chromepet/mc=Chennai?bedroom=1BHK&maxBudget=15000",
    "https://www.magicbricks.com/property-for-rent/residential-rent/flats-in-Pallavaram/mc=Chennai?bedroom=1BHK&maxBudget=15000",
    "https://www.magicbricks.com/property-for-rent/residential-rent/flats-in-Tambaram/mc=Chennai?bedroom=1BHK&maxBudget=15000",
    "https://www.magicbricks.com/property-for-rent/residential-rent/flats-in-Nanganallur/mc=Chennai?bedroom=1BHK&maxBudget=15000",
]

CARD_SELECTOR = ".mb-srp__card, [class*='mb-srp__card'], [data-id]"


def extract_id(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "propertyId" in qs:
        return qs["propertyId"][0]
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_url(ctx, url: str) -> list[Listing]:
    listings = []
    area = url.split("flats-in-")[1].split("/")[0] if "flats-in-" in url else "?"
    page = await new_stealth_page(ctx)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector(CARD_SELECTOR, timeout=15000)
        except Exception:
            await page.wait_for_timeout(5000)

        cards = await page.query_selector_all(CARD_SELECTOR)
        logger.info("MagicBricks [%s]: found %d cards", area, len(cards))

        for card in cards:
            try:
                url_el = await card.query_selector("a")
                if not url_el:
                    continue
                href = await url_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = "https://www.magicbricks.com" + href
                listing_id = extract_id(href)

                title_el = await card.query_selector(
                    ".mb-srp__card--title, [class*='card--title'], h2, h3"
                )
                title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                price_el = await card.query_selector(
                    ".mb-srp__card--price, [class*='card--price'], [class*='price']"
                )
                price = parse_price(await price_el.inner_text()) if price_el else None
                if price is None:
                    continue

                addr_el = await card.query_selector(
                    ".mb-srp__card--locality, [class*='locality'], [class*='location']"
                )
                address = (
                    (await addr_el.inner_text()).strip() if addr_el else f"{area}, Chennai"
                )

                img_els = await card.query_selector_all("img[src]")
                images = [
                    src for img in img_els[:3]
                    if (src := await img.get_attribute("src")) and not src.startswith("data:")
                ]

                listings.append(Listing(
                    id=listing_id, source="magicbricks", title=title,
                    address=address, price=price, url=href, images=images,
                ))
            except Exception:
                logger.exception("Error parsing MagicBricks card")
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
                logger.exception("MagicBricks failed for URL: %s", url)
    logger.info("MagicBricks total unique: %d", len(all_listings))
    return all_listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())

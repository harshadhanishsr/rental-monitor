import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context, new_stealth_page

logger = logging.getLogger(__name__)

# Quikr — multiple areas near Chromepet office
SEARCH_URLS = [
    "https://www.quikr.com/homes/flats-for-rent-in-chromepet+chennai?category_id=2&sub_category=1bhk&max_price=15000",
    "https://www.quikr.com/homes/flats-for-rent-in-pallavaram+chennai?category_id=2&sub_category=1bhk&max_price=15000",
    "https://www.quikr.com/homes/flats-for-rent-in-tambaram+chennai?category_id=2&sub_category=1bhk&max_price=15000",
]

CARD_SELECTOR = (
    ".product-info, [class*='listing-card'], "
    "[class*='QuikrCard'], [class*='productCard']"
)

_ID_PATTERN = re.compile(r"(\d{6,})(?:/|$|\?)")


def extract_id(url: str) -> str:
    match = _ID_PATTERN.search(url)
    return match.group(1) if match else url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_url(ctx, url: str) -> list[Listing]:
    listings = []
    area = url.split("flats-for-rent-in-")[1].split("+")[0] if "flats-for-rent-in-" in url else "?"
    page = await new_stealth_page(ctx)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector(
                ".product-info, [class*='listing-card'], [class*='card'], "
                "[class*='quikr-card']",
                timeout=15000,
            )
        except Exception:
            await page.wait_for_timeout(5000)

        cards = await page.query_selector_all(CARD_SELECTOR)
        logger.info("Quikr [%s]: found %d cards", area, len(cards))

        for card in cards:
            try:
                url_el = await card.query_selector("a")
                if not url_el:
                    continue
                href = await url_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = "https://www.quikr.com" + href
                listing_id = extract_id(href)

                title_el = await card.query_selector(
                    "h2, h3, .product-title, [class*='title']"
                )
                title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                price_el = await card.query_selector(
                    ".product-price, [class*='price'], [class*='Price']"
                )
                price = parse_price(await price_el.inner_text()) if price_el else None
                if price is None:
                    continue

                addr_el = await card.query_selector(
                    ".product-locality, [class*='location'], [class*='locality']"
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
                    id=listing_id, source="quikr", title=title,
                    address=address, price=price, url=href, images=images,
                ))
            except Exception:
                logger.exception("Error parsing Quikr card")
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
                logger.exception("Quikr failed for URL: %s", url)
    logger.info("Quikr total unique: %d", len(all_listings))
    return all_listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())

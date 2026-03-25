import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context, new_stealth_page

logger = logging.getLogger(__name__)

# Housing.com — multiple areas near Chromepet office
SEARCH_URLS = [
    "https://housing.com/in/rent/1-rk-studio-in-chromepet-chennai?bedroom=1&max_budget=15000",
    "https://housing.com/in/rent/1-rk-studio-in-pallavaram-chennai?bedroom=1&max_budget=15000",
    "https://housing.com/in/rent/1-rk-studio-in-tambaram-chennai?bedroom=1&max_budget=15000",
    "https://housing.com/in/rent/1-rk-studio-in-nanganallur-chennai?bedroom=1&max_budget=15000",
]

CARD_SELECTOR = (
    "[class*='propertyCard'], [class*='PropertyCard'], "
    "[data-testid*='card'], [class*='listing-card']"
)


def extract_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_url(ctx, url: str) -> list[Listing]:
    listings = []
    area = url.split("in-")[1].split("-chennai")[0] if "in-" in url else "?"
    page = await new_stealth_page(ctx)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector(
                "[class*='propertyCard'], [class*='PropertyCard'], "
                "[data-testid*='card'], [class*='listing']",
                timeout=15000,
            )
        except Exception:
            await page.wait_for_timeout(5000)

        cards = await page.query_selector_all(CARD_SELECTOR)
        logger.info("Housing.com [%s]: found %d cards", area, len(cards))

        for card in cards:
            try:
                url_el = await card.query_selector("a")
                if not url_el:
                    continue
                href = await url_el.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = "https://housing.com" + href
                listing_id = extract_id(href)

                title_el = await card.query_selector(
                    "h2, h3, [class*='title'], [class*='Title']"
                )
                title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                price_el = await card.query_selector(
                    "[class*='price'], [class*='Price'], [class*='rent'], [class*='Rent']"
                )
                price = parse_price(await price_el.inner_text()) if price_el else None
                if price is None:
                    continue

                addr_el = await card.query_selector(
                    "[class*='locality'], [class*='Locality'], "
                    "[class*='address'], [class*='location']"
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
                    id=listing_id, source="housing", title=title,
                    address=address, price=price, url=href, images=images,
                ))
            except Exception:
                logger.exception("Error parsing Housing.com card")
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
                logger.exception("Housing.com failed for URL: %s", url)
    logger.info("Housing.com total unique: %d", len(all_listings))
    return all_listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())

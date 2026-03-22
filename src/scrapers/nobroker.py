import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.nobroker.in/property/rental/chennai/Chromepet"
    "?bedroom=1&budget=15000"
)


def extract_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            cards = await page.query_selector_all(".srpPropertyCard, [data-testid='property-card']")
            for card in cards:
                try:
                    url_el = await card.query_selector("a[href*='/property/']")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://www.nobroker.in" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector(".property-title, h3, h4")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector(".price, [data-testid='price']")
                    price_text = (await price_el.inner_text()).strip() if price_el else ""
                    price = parse_price(price_text)
                    if price is None:
                        continue

                    addr_el = await card.query_selector(".location, [data-testid='location']")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img[src*='nobroker']")
                    images = []
                    for img in img_els[:3]:
                        src = await img.get_attribute("src")
                        if src:
                            images.append(src)

                    listings.append(Listing(
                        id=listing_id,
                        source="nobroker",
                        title=title,
                        address=address,
                        price=price,
                        url=url,
                        images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing NoBroker card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())

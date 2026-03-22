import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.99acres.com/1-bhk-flat-for-rent-in-chromepet-chennai-ffid"
    "?budget_max=15000"
)

_ID_PATTERN = re.compile(r"-([A-Z0-9]+)-\d+$")


def extract_id(url: str) -> str:
    match = _ID_PATTERN.search(url)
    if match:
        return match.group(1)
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
            cards = await page.query_selector_all(".tuple__wrapper, [class*='projectTuple']")
            for card in cards:
                try:
                    url_el = await card.query_selector("a[href*='99acres.com']")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://www.99acres.com" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector(".tuple__title, h2")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector(".tuple__price-details-text, .priceVal")
                    price = parse_price(await price_el.inner_text()) if price_el else None
                    if price is None:
                        continue

                    addr_el = await card.query_selector(".tuple__location-text")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img[src]")
                    images = [await i.get_attribute("src") for i in img_els[:3] if await i.get_attribute("src")]

                    listings.append(Listing(
                        id=listing_id, source="99acres", title=title,
                        address=address, price=price, url=url, images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing 99acres card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())

"""
Find the correct 99acres Chennai city code and inspect card HTML for selectors.
"""
import asyncio
import sys
sys.path.insert(0, '/app')
from src.scrapers.base import get_browser_context, new_stealth_page

# Chennai city codes to try
CITY_TESTS = {
    "city_7":  "https://www.99acres.com/search/property/rent/residential/chennai?city=7&preference=R&bedroom=1&area_name=Chromepet",
    "city_10": "https://www.99acres.com/search/property/rent/residential/chennai?city=10&preference=R&bedroom=1&area_name=Chromepet",
    "city_12": "https://www.99acres.com/search/property/rent/residential/chennai?city=12&preference=R&bedroom=1&area_name=Chromepet",
    "no_city": "https://www.99acres.com/search/property/rent/residential/chennai?preference=R&bedroom=1&area_name=Chromepet",
}

CARD_SEL = "[class*='tupleNew'], [class*='tuple__wrap']"


async def inspect_cards():
    async with get_browser_context() as ctx:
        for name, url in CITY_TESTS.items():
            page = await new_stealth_page(ctx)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_selector(CARD_SEL, timeout=15000)
                except Exception:
                    await page.wait_for_timeout(4000)

                title = await page.title()
                cards = await page.query_selector_all(CARD_SEL)
                print(f"\n{name}: {title[:60]}")
                print(f"  Cards: {len(cards)}")
                if cards:
                    html = await cards[0].inner_html()
                    print(f"  First card (1500 chars):\n{html[:1500]}")
            except Exception as e:
                print(f"\n{name}: ERROR: {e}")
            finally:
                await page.close()


if __name__ == "__main__":
    asyncio.run(inspect_cards())

"""Test the correct 99acres rent URL path."""
import asyncio
import sys
sys.path.insert(0, '/app')
from src.scrapers.base import get_browser_context, new_stealth_page

URLS = {
    "buy_working": "https://www.99acres.com/search/property/buy/residential/chennai?city=2&preference=S&category=1&bedroom=1&max_budget=15000&area_name=Chromepet",
    "rent_v1": "https://www.99acres.com/search/property/rent/residential/chennai?city=2&preference=R&bedroom=1&max_budget=15000&area_name=Chromepet",
    "rent_v2": "https://www.99acres.com/search/property/rent/residential/chennai?city=2&bedroom=1&budget_max=15000&area_name=Chromepet",
    "rent_v3": "https://www.99acres.com/search/property/rent/residential/chennai?bedroom=1&area_name=Chromepet&budget_max=15000",
}


async def test_with_context():
    async with get_browser_context() as ctx:
        for name, url in URLS.items():
            page = await new_stealth_page(ctx)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_selector(
                        ".tuple__wrapper, [class*='projectTuple'], [class*='Tuple']",
                        timeout=15000,
                    )
                except Exception:
                    await page.wait_for_timeout(4000)

                title = await page.title()
                cards = await page.query_selector_all(
                    ".tuple__wrapper, [class*='projectTuple'], [class*='Tuple']"
                )
                body = await page.evaluate("document.body.innerText")
                print(f"\n{name}: {url[:70]}")
                print(f"  Title: {title[:60]}")
                print(f"  Cards: {len(cards)}")
                if cards:
                    html = await cards[0].inner_html()
                    print(f"  First card: {html[:500]}")
                else:
                    print(f"  Body: {body[:300]}")
            except Exception as e:
                print(f"\n{name}: ERROR: {e}")
            finally:
                await page.close()


if __name__ == "__main__":
    asyncio.run(test_with_context())

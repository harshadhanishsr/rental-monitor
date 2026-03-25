"""
Navigate 99acres via homepage → rent search to find the correct URL structure
and test the scraper with the proper context setup.
"""
import asyncio
import sys
sys.path.insert(0, '/app')
from src.scrapers.base import get_browser_context, new_stealth_page

# Try navigating from homepage to set cookies first, then search
HOMEPAGE = "https://www.99acres.com/"
RENT_URLS = [
    "https://www.99acres.com/1-bhk-flats-for-rent-in-chromepet-ffid",
    "https://www.99acres.com/1-bhk-flat-for-rent-in-chromepet-ffid",
    "https://www.99acres.com/residential-for-rent-in-chromepet-chennai-ffid?bedroom=1BHK&budget=0-15000",
    "https://www.99acres.com/flats-for-rent-in-chromepet-ffid?bedroom=1BHK",
    "https://www.99acres.com/search/property?city=2&preference=R&bedroom=1&area_name=Chromepet",
]


async def test_with_context():
    async with get_browser_context() as ctx:
        page = await new_stealth_page(ctx)

        # Set up session by visiting homepage first
        print("Visiting homepage to set session...")
        try:
            await page.goto(HOMEPAGE, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            print(f"Homepage loaded: {await page.title()}")
        except Exception as e:
            print(f"Homepage error: {e}")

        # Now test rent URLs
        for url in RENT_URLS:
            page2 = await new_stealth_page(ctx)
            try:
                await page2.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page2.wait_for_selector(
                        ".tuple__wrapper, [class*='projectTuple'], [class*='Tuple']",
                        timeout=10000,
                    )
                except Exception:
                    await page2.wait_for_timeout(3000)

                title = await page2.title()
                final_url = page2.url
                cards = await page2.query_selector_all(
                    ".tuple__wrapper, [class*='projectTuple'], [class*='Tuple']"
                )
                body = await page2.evaluate("document.body.innerText")
                print(f"\nURL: {url[:70]}")
                print(f"  Title: {title[:60]}")
                print(f"  Final: {final_url[:70]}")
                print(f"  Cards: {len(cards)}")
                if cards:
                    html = await cards[0].inner_html()
                    print(f"  First card: {html[:300]}")
                else:
                    print(f"  Body: {body[:200]}")
            except Exception as e:
                print(f"\nURL: {url[:70]}")
                print(f"  ERROR: {e}")
            finally:
                await page2.close()


if __name__ == "__main__":
    asyncio.run(test_with_context())

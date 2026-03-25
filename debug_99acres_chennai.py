"""
Find the correct 99acres Chennai city code by testing more codes
and by navigating via their site search to capture the actual URL.
"""
import asyncio
import sys
sys.path.insert(0, '/app')
from src.scrapers.base import get_browser_context, new_stealth_page

# Test more city codes for Chennai
CITY_CODES = [4, 5, 6, 8, 9, 11, 13, 14, 15, 16, 17, 18, 20]
BASE = "https://www.99acres.com/search/property/rent/residential/chennai?preference=R&bedroom=1&area_name=Chromepet&city={}"


async def find_chennai_code():
    async with get_browser_context() as ctx:
        print("Testing city codes for Chennai:")
        for code in CITY_CODES:
            url = BASE.format(code)
            page = await new_stealth_page(ctx)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)
                title = await page.title()
                body_preview = await page.evaluate("document.body.innerText")
                print(f"  city={code:3d}: {title[:70]}")
                if "chennai" in title.lower() or "chromepet" in body_preview.lower():
                    print(f"    *** POSSIBLE MATCH ***")
                    print(f"    Body: {body_preview[:200]}")
            except Exception as e:
                print(f"  city={code:3d}: ERROR: {str(e)[:50]}")
            finally:
                await page.close()

        # Also try: navigate from homepage and search
        print("\n\nNavigating via search form...")
        page = await new_stealth_page(ctx)
        try:
            await page.goto("https://www.99acres.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # Try clicking "Rent" tab if exists
            rent_btn = await page.query_selector("text=Rent, [data-tab='rent'], [class*='rent']")
            if rent_btn:
                await rent_btn.click()
                await page.wait_for_timeout(1000)

            print(f"Homepage title: {await page.title()}")

            # Get any visible search input and type Chennai Chromepet
            inputs = await page.query_selector_all("input[type='text'], input[placeholder*='location'], input[placeholder*='city']")
            print(f"Found {len(inputs)} text inputs")
            for i, inp in enumerate(inputs[:3]):
                placeholder = await inp.get_attribute("placeholder") or ""
                name = await inp.get_attribute("name") or ""
                print(f"  Input {i}: placeholder='{placeholder}' name='{name}'")
        finally:
            await page.close()


if __name__ == "__main__":
    asyncio.run(find_chennai_code())

"""Find Chennai city code by testing codes 19, 21-35."""
import asyncio
import sys
sys.path.insert(0, '/app')
from src.scrapers.base import get_browser_context, new_stealth_page

BASE = "https://www.99acres.com/search/property/rent/residential/chennai?preference=R&bedroom=1&area_name=Chromepet&city={}"
CODES = [19, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 35, 40, 45, 50]


async def scan():
    async with get_browser_context() as ctx:
        for code in CODES:
            page = await new_stealth_page(ctx)
            try:
                await page.goto(BASE.format(code), wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1500)
                title = await page.title()
                print(f"city={code:3d}: {title[:80]}")
                if "chennai" in title.lower() or "chromepet" in title.lower():
                    print(f"  *** FOUND CHENNAI: city={code} ***")
                    body = await page.evaluate("document.body.innerText")
                    print(f"  Body: {body[:300]}")
            except Exception as e:
                print(f"city={code:3d}: ERROR: {str(e)[:50]}")
            finally:
                await page.close()


if __name__ == "__main__":
    asyncio.run(scan())

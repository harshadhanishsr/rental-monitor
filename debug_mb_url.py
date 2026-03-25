"""Test different MagicBricks URL formats to find which one works."""
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.29 Safari/537.36"
SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'

CANDIDATES = [
    "https://www.magicbricks.com/1-bhk-flats-for-rent-in-chromepet-chennai-pppfth.html",
    "https://www.magicbricks.com/property-for-rent/1bhk/chromepet/chennai",
    "https://www.magicbricks.com/flats-for-rent-in-chromepet/1-bhk/chennai-city",
    "https://www.magicbricks.com/propertyfor=rent/1-BHK/locality=chromepet/state=Tamil-Nadu/city=Chennai",
    "https://www.magicbricks.com/property-for-rent/1-bhk-flats-in-Chromepet-Chennai",
    "https://www.magicbricks.com/property-for-rent/residential-rent/flats-in-Chromepet-Chennai?bedroom=1BHK&BudgetMax=15000",
]


async def test_url(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-IN,en-GB;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Sec-CH-UA": SEC_CH_UA,
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            },
        )
        page = await ctx.new_page()
        await stealth_async(page)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            title = await page.title()
            final = page.url
            # Count any element that looks like a property card
            cards = await page.query_selector_all(
                ".mb-srp__card, [class*='mb-srp__card'], [class*='property'], "
                "article, [class*='card']"
            )
            print(f"  {len(cards):3d} cards | {title[:50]:50s} | {final[:80]}")
        except Exception as e:
            print(f"  ERR | {str(e)[:60]}")
        finally:
            await browser.close()


async def main():
    print(f"\nTesting MagicBricks URL formats:")
    print(f"{'Cards':>7} | {'Title':50s} | Final URL")
    print("-" * 120)
    for url in CANDIDATES:
        await test_url(url)


if __name__ == "__main__":
    asyncio.run(main())

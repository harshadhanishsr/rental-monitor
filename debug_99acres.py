"""Inspect 99acres with various rent URL formats to find one that works."""
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.29 Safari/537.36"
SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'

URLS = {
    "rent_R": "https://www.99acres.com/search/property?city=2&preference=R&bedroom=1&min_budget=1000&max_budget=15000&area_name=Chromepet",
    "rent_RL": "https://www.99acres.com/search/property?city=2&preference=RL&bedroom=1&area_name=Chromepet",
    "rent_R_no_budget": "https://www.99acres.com/search/property?city=2&preference=R&bedroom=1&area_name=Chromepet",
    "rent_old": "https://www.99acres.com/1-bhk-flat-for-rent-in-chromepet-chennai-ffid?budget_max=15000",
    "sale_working": "https://www.99acres.com/search/property?city=2&preference=S&category=1&bedroom=1&max_budget=15000&area_name=Chromepet",
}


async def test(name, url):
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
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_selector(".tuple__wrapper, [class*='Tuple'], [class*='tuple']", timeout=10000)
            except Exception:
                await page.wait_for_timeout(3000)

            title = await page.title()
            cards = await page.query_selector_all(".tuple__wrapper, [class*='projectTuple'], [class*='Tuple']")
            body = await page.evaluate("document.body.innerText")

            print(f"\n--- {name} ---")
            print(f"Title: {title}")
            print(f"Final URL: {page.url}")
            print(f"Cards: {len(cards)}")
            print(f"Body preview: {body[:300]}")

            if cards:
                html = await cards[0].inner_html()
                print(f"\nFirst card HTML (500 chars): {html[:500]}")
        except Exception as e:
            print(f"\n--- {name} ---\nERROR: {e}")
        finally:
            await browser.close()


async def main():
    for name, url in URLS.items():
        await test(name, url)

if __name__ == "__main__":
    asyncio.run(main())

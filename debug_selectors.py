"""
Inspect actual card HTML for sites that are partially working.
Run: docker exec rental-monitor-rental-monitor-1 python debug_selectors.py
"""
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

SITES = {
    "nobroker": "https://www.nobroker.in/property/rental/chennai/Chromepet?bedroom=1&budget=15000",
    "magicbricks": (
        "https://www.magicbricks.com/property-for-rent/residential-rent/"
        "flats-in-Chromepet/mc=Chennai?bedroom=1BHK&maxBudget=15000"
    ),
    "acres99_new": (
        "https://www.99acres.com/search/property?city=2&preference=S&category=1"
        "&bedroom=1&max_budget=15000&area_name=Chromepet"
    ),
    "quikr_new": (
        "https://www.quikr.com/homes/flats-for-rent-in-chromepet+chennai"
        "?category_id=2&sub_category=1bhk&max_price=15000"
    ),
}


async def inspect(name: str, url: str, card_selector: str):
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
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            },
        )
        page = await ctx.new_page()
        await stealth_async(page)
        print(f"\n{'='*60}")
        print(f"  {name.upper()}")
        print(f"{'='*60}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            print(f"Title: {await page.title()}")
            print(f"URL:   {page.url}")

            cards = await page.query_selector_all(card_selector)
            print(f"Cards found with '{card_selector}': {len(cards)}")

            if cards:
                # Print inner HTML of first card
                html = await cards[0].inner_html()
                print(f"\n--- First card inner HTML (first 2000 chars) ---")
                print(html[:2000])
            else:
                # Print all class names on page
                all_classes = await page.evaluate("""
                    () => {
                        const seen = new Set();
                        document.querySelectorAll('[class]').forEach(el => {
                            (typeof el.className === 'string' ? el.className : '').split(/\\s+/).forEach(c => {
                                if (c.length > 3) seen.add(c);
                            });
                        });
                        return [...seen].slice(0, 100);
                    }
                """)
                print(f"Page classes: {', '.join(all_classes)}")
                body = await page.evaluate("document.body.innerText")
                print(f"\nBody text (first 500 chars): {body[:500]}")
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            await browser.close()


async def main():
    await inspect(
        "nobroker",
        SITES["nobroker"],
        ".srpPropertyCard, [data-testid='property-card'], .property-tile, [class*='PropertyTile']",
    )
    await inspect(
        "magicbricks",
        SITES["magicbricks"],
        ".mb-srp__card, [class*='mb-srp__card'], [data-id]",
    )
    await inspect(
        "acres99_new",
        SITES["acres99_new"],
        ".tuple__wrapper, [class*='projectTuple'], [class*='Tuple']",
    )
    await inspect(
        "quikr_new",
        SITES["quikr_new"],
        ".product-info, [class*='listing-card'], [class*='QuikrCard'], [class*='productCard']",
    )


if __name__ == "__main__":
    asyncio.run(main())

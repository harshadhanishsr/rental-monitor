"""
Diagnostic script — dumps HTML and key element info from each rental site.
Run inside the container: docker exec -it <container> python debug_scrapers.py
"""
import asyncio
import os
from playwright.async_api import async_playwright

SITES = {
    "nobroker": (
        "https://www.nobroker.in/property/rental/chennai/Chromepet"
        "?bedroom=1&budget=15000"
    ),
    "magicbricks": (
        "https://www.magicbricks.com/property-for-rent/1-BHK-flats-in-Chromepet-Chennai"
        "?proptype=Multistorey-Apartment,Builder-Floor-Apartment,Penthouse,Studio-Apartment"
        "&BudgetMax=15000"
    ),
    "acres99": (
        "https://www.99acres.com/1-bhk-flat-for-rent-in-chromepet-chennai-ffid"
        "?budget_max=15000"
    ),
    "olx": (
        "https://www.olx.in/chennai_g4058979/q-1-bhk-chromepet"
        "?filter=price_max_1500000"
    ),
    "housing": (
        "https://housing.com/in/rent/1bhk-flats-in-chromepet-chennai"
        "?f_budget_max=15000"
    ),
    "quikr": (
        "https://www.quikr.com/homes/1-bhk-flat-for-rent-in-chromepet-chennai"
        "?maxPrice=15000"
    ),
}

OUT_DIR = "/app/data"


async def debug_site(name: str, url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        )
        page = await ctx.new_page()
        try:
            print(f"\n{'='*60}")
            print(f"  {name.upper()}")
            print(f"{'='*60}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)

            final_url = page.url
            title = await page.title()
            html = await page.content()

            html_path = os.path.join(OUT_DIR, f"debug_{name}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

            print(f"Title   : {title}")
            print(f"Final URL: {final_url}")
            print(f"HTML len : {len(html):,} chars → saved to {html_path}")

            # Print unique class substrings that look like listing containers
            classes = await page.evaluate("""
                () => {
                    const seen = new Set();
                    document.querySelectorAll('[class]').forEach(el => {
                        el.className.split(/\\s+/).forEach(c => {
                            if (c.length > 3) seen.add(c);
                        });
                    });
                    return [...seen].slice(0, 80);
                }
            """)
            print(f"Classes (first 80): {', '.join(classes)}")

            # Body text preview
            body = await page.evaluate("document.body.innerText")
            print(f"\nBody text (first 500 chars):\n{body[:500]}")

        except Exception as exc:
            print(f"ERROR: {exc}")
        finally:
            await browser.close()


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, url in SITES.items():
        await debug_site(name, url)


if __name__ == "__main__":
    asyncio.run(main())

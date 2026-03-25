"""
Intercept XHR/fetch API calls made by each rental site.
This reveals their internal REST APIs so we can call them directly.
Run: docker exec rental-monitor-rental-monitor-1 python debug_api_intercept.py
"""
import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

URLS = {
    "nobroker": "https://www.nobroker.in/property/rental/chennai/Chromepet?bedroom=1&budget=15000",
    "magicbricks": "https://www.magicbricks.com/property-for-rent/1-bhk-flats-for-rent-in-Chromepet-Chennai",
}


async def intercept_site(name: str, url: str):
    api_calls = []

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

        # Intercept all requests
        async def on_request(request):
            if request.resource_type in ("xhr", "fetch"):
                req_url = request.url
                # Filter to likely API calls (json, api, search, property)
                keywords = ["api", "search", "property", "listing", "rent", "json", "graphql"]
                if any(k in req_url.lower() for k in keywords):
                    api_calls.append({
                        "method": request.method,
                        "url": req_url,
                        "post_data": request.post_data,
                    })

        page.on("request", on_request)

        print(f"\n{'='*60}")
        print(f"  {name.upper()} — intercepting API calls")
        print(f"{'='*60}")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6000)
            print(f"Final URL: {page.url}")
            print(f"\nAPI calls intercepted ({len(api_calls)}):")
            for call in api_calls[:20]:
                print(f"  [{call['method']}] {call['url']}")
                if call["post_data"]:
                    print(f"    Body: {call['post_data'][:200]}")

            # Also save full list
            with open(f"/app/data/api_calls_{name}.json", "w") as f:
                json.dump(api_calls, f, indent=2)
            print(f"\n  Full list saved to /app/data/api_calls_{name}.json")

        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            await browser.close()


async def main():
    for name, url in URLS.items():
        await intercept_site(name, url)


if __name__ == "__main__":
    asyncio.run(main())

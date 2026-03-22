from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext


@asynccontextmanager
async def get_browser_context():
    """Yields a Playwright browser context with realistic headers."""
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        try:
            yield context
        finally:
            await browser.close()

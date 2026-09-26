from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth as _Stealth
_stealth = _Stealth()

# Match the Chromium version we're using
_CHROME_VER = "124.0.6367.29"
_CHROME_MAJOR = "124"

# Sec-CH-UA that represents a real Chrome (not HeadlessChrome)
_SEC_CH_UA = (
    f'"Chromium";v="{_CHROME_MAJOR}", '
    f'"Google Chrome";v="{_CHROME_MAJOR}", '
    '"Not-A.Brand";v="99"'
)

# JS override injected before any page script runs — removes "HeadlessChrome"
# from navigator.userAgentData, which sites read via JS API
_USERAGENT_OVERRIDE = f"""
Object.defineProperty(navigator, 'userAgentData', {{
    get: () => ({{
        brands: [
            {{ brand: 'Chromium', version: '{_CHROME_MAJOR}' }},
            {{ brand: 'Google Chrome', version: '{_CHROME_MAJOR}' }},
            {{ brand: 'Not-A.Brand', version: '99' }},
        ],
        mobile: false,
        platform: 'Windows',
        getHighEntropyValues: (hints) => Promise.resolve({{
            architecture: 'x86',
            bitness: '64',
            brands: [
                {{ brand: 'Chromium', version: '{_CHROME_VER}' }},
                {{ brand: 'Google Chrome', version: '{_CHROME_VER}' }},
                {{ brand: 'Not-A.Brand', version: '99.0.0.0' }},
            ],
            fullVersionList: [
                {{ brand: 'Chromium', version: '{_CHROME_VER}' }},
                {{ brand: 'Google Chrome', version: '{_CHROME_VER}' }},
                {{ brand: 'Not-A.Brand', version: '99.0.0.0' }},
            ],
            mobile: false,
            model: '',
            platform: 'Windows',
            platformVersion: '15.0.0',
            uaFullVersion: '{_CHROME_VER}',
        }}),
        toJSON: () => ({{
            brands: [
                {{ brand: 'Chromium', version: '{_CHROME_MAJOR}' }},
                {{ brand: 'Google Chrome', version: '{_CHROME_MAJOR}' }},
                {{ brand: 'Not-A.Brand', version: '99' }},
            ],
            mobile: false,
            platform: 'Windows',
        }}),
    }}),
}});
"""


@asynccontextmanager
async def get_browser_context():
    """Yields a Playwright browser context configured to look like a real Chrome."""
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context: BrowserContext = await browser.new_context(
            user_agent=(
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{_CHROME_VER} Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                # Override Sec-CH-UA client hints to hide HeadlessChrome
                "Sec-CH-UA": _SEC_CH_UA,
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        # Inject userAgentData override before any page JS runs
        await context.add_init_script(_USERAGENT_OVERRIDE)
        try:
            yield context
        finally:
            await browser.close()


async def new_stealth_page(ctx: BrowserContext) -> Page:
    """Create a new page with playwright-stealth applied."""
    page = await ctx.new_page()
    await _stealth.apply_stealth_async(page)
    return page

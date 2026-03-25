"""
Dump complete HTML of first 2 Chennai 99acres cards to find correct selectors.
"""
import asyncio
import sys
sys.path.insert(0, '/app')
from src.scrapers.base import get_browser_context, new_stealth_page

URL = (
    "https://www.99acres.com/search/property/rent/residential/chennai"
    "?city=32&preference=R&bedroom=1&area_name=Chromepet&budget_max=15000"
)


async def dump_cards():
    async with get_browser_context() as ctx:
        page = await new_stealth_page(ctx)
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_selector("[class*='tupleNew__tupleWrap']", timeout=15000)
        except Exception:
            await page.wait_for_timeout(5000)

        cards = await page.query_selector_all("[class*='tupleNew__tupleWrap']")
        print(f"Total cards: {len(cards)}")

        # Dump full HTML of first 2 cards
        for i, card in enumerate(cards[:2]):
            html = await card.inner_html()
            print(f"\n\n{'='*60}")
            print(f"CARD {i+1} (full HTML):")
            print(f"{'='*60}")
            print(html)

        await page.close()


if __name__ == "__main__":
    asyncio.run(dump_cards())

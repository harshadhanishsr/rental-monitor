"""Usage: uv run python scripts/refresh_fixtures.py <source>

Some sources block plain httpx and require curl_cffi Chrome impersonation.
Mark those by setting ``cffi=True`` in the URLS entry.
"""
import asyncio
import sys
from pathlib import Path
from src.core.http import AsyncHttp

URLS: dict[str, dict] = {
    "sulekha": {
        "cffi": False,
        "pages": [
            ("pallavaram",
             "https://property.sulekha.com/1-bhk-apartments-flats-for-rent/chennai/pallavaram"),
        ],
    },
    "squareyards": {
        "cffi": False,
        "pages": [
            ("pallavaram",
             "https://www.squareyards.com/rent/1-bhk-for-rent-in-pallavaram-chennai"),
        ],
    },
    "commonfloor": {
        "cffi": True,
        "pages": [
            ("pallavaram",
             "https://www.commonfloor.com/pallavaram-chennai-property/for-rent?bedroom=1"),
        ],
    },
    "ninetynine_acres": {
        "cffi": True,
        "pages": [
            ("pallavaram",
             "https://www.99acres.com/search/property/rent/residential/chennai?city=32&preference=R&bedroom=1&budget_max=15000"),
        ],
    },
}


async def _fetch_cffi(url: str) -> tuple[int, str]:
    from curl_cffi.requests import AsyncSession
    async with AsyncSession(impersonate="chrome110") as s:
        r = await s.get(url, headers={"Accept-Language": "en-IN,en;q=0.9"})
        return r.status_code, r.text


async def _fetch_httpx(url: str) -> tuple[int, str]:
    async with AsyncHttp() as http:
        r = await http.get(url)
        return r.status_code, r.text


async def main(source: str):
    entry = URLS[source]
    out = Path(f"tests/fixtures/{source}")
    out.mkdir(parents=True, exist_ok=True)
    fetch = _fetch_cffi if entry.get("cffi") else _fetch_httpx
    for name, url in entry["pages"]:
        status, text = await fetch(url)
        (out / f"{name}.html").write_text(text, encoding="utf-8")
        print(f"saved {name}.html ({len(text)} chars, status={status})")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))

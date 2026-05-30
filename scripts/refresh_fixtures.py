"""Usage: uv run python scripts/refresh_fixtures.py <source>"""
import asyncio
import sys
from pathlib import Path
from src.core.http import AsyncHttp

URLS = {
    "sulekha": [
        ("pallavaram",
         "https://property.sulekha.com/1-bhk-apartments-flats-for-rent/chennai/pallavaram"),
    ],
}


async def main(source: str):
    out = Path(f"tests/fixtures/{source}")
    out.mkdir(parents=True, exist_ok=True)
    async with AsyncHttp() as http:
        for name, url in URLS[source]:
            r = await http.get(url)
            (out / f"{name}.html").write_text(r.text, encoding="utf-8")
            print(f"saved {name}.html ({len(r.text)} chars, status={r.status_code})")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))

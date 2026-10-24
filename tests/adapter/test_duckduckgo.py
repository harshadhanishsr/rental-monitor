from pathlib import Path
from src.sources.duckduckgo import DuckDuckGo

FIXTURE = Path("tests/fixtures/duckduckgo/synthetic.html").read_text(encoding="utf-8")


def test_ddg_parse_extracts_listings_and_filters_non_listings():
    """The Wikipedia entry must be filtered out; the three listing-domain
    results survive with prices recovered from their snippets."""
    listings = DuckDuckGo()._parse(FIXTURE)
    assert len(listings) == 3
    assert all(l.source == "duckduckgo" for l in listings)
    assert all(l.price > 0 for l in listings)
    origins = sorted(l.also_seen_on[0] for l in listings)
    assert origins == ["magicbricks", "nobroker", "olx"]

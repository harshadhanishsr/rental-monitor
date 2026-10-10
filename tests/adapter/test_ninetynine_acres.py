from pathlib import Path
from src.sources.ninetynine_acres import NinetyNineAcres

FIXTURE = Path("tests/fixtures/ninetynine_acres/pallavaram.html").read_text(encoding="utf-8")


def test_99acres_parse_extracts_listings_with_price():
    """Apartments and RentActions live in separate JSON-LD blocks; the parser
    must join them by ``name``."""
    listings = NinetyNineAcres()._parse(FIXTURE)
    assert len(listings) > 0
    assert all(l.source == "99acres" for l in listings)
    assert all(l.price > 0 for l in listings)
    assert all(l.id.startswith("99acres_") for l in listings)

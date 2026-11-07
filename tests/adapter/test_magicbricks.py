from pathlib import Path
from src.sources.magicbricks import MagicBricks

FIXTURE = Path("tests/fixtures/magicbricks/pallavaram.html").read_text(encoding="utf-8")


def test_magicbricks_parse_extracts_from_preloaded_state():
    """Listings live inside ``window.SERVER_PRELOADED_STATE_.nsrResultList``."""
    listings = MagicBricks()._parse(FIXTURE)
    assert len(listings) > 0
    assert all(l.source == "magicbricks" for l in listings)
    assert all(l.price > 0 for l in listings)
    assert all(l.id.startswith("magicbricks_") for l in listings)
    # at least one entry should expose geo
    assert any(l.lat is not None and l.lng is not None for l in listings)

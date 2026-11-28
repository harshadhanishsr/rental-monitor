from pathlib import Path
from src.sources.olx import OLX

FIXTURE = Path("tests/fixtures/olx/pallavaram.html").read_text(encoding="utf-8")


def test_olx_parse_extracts_per_ad_objects_from_window_app():
    """Outer ``window.__APP`` is a JS literal, but each ad sub-object is strict
    JSON and is recovered by bracket-counting from ``"<id>":{"id":"<id>"``."""
    listings = OLX()._parse(FIXTURE)
    assert len(listings) > 0
    assert all(l.source == "olx" for l in listings)
    assert all(l.price > 0 for l in listings)
    assert all(l.id.startswith("olx_") for l in listings)
    # SSR ItemList provides canonical iid- slug URLs
    assert all("iid-" in l.url for l in listings)
    # At least one ad should carry geo from ``locations[0].lat/lon``
    assert any(l.lat is not None and l.lng is not None for l in listings)

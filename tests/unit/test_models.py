from src.models import Listing


def test_listing_round_trip():
    src = {"id": "sulekha_1", "source": "sulekha", "title": "1BHK Pallavaram",
           "address": "Pallavaram, Chennai", "price": 12000,
           "url": "https://x", "lat": 13.0, "lng": 80.1}
    l = Listing.model_validate(src)
    assert l.also_seen_on == []
    assert Listing.model_validate_json(l.model_dump_json()) == l


def test_listing_rejects_negative_price():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Listing(id="x", source="y", title="t", address="a",
                price=-1, url="https://x")

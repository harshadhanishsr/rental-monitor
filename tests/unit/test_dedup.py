from src.models import Listing
from src.pipeline.dedup import fingerprint, merge

A = Listing(id="sulekha_1", source="sulekha", title="1BHK Pallavaram",
            address="123 Foo St, Pallavaram, Chennai", price=11800,
            url="https://s/1", lat=12.974, lng=80.143, furnishing="semi-furnished")
B = Listing(id="99acres_2", source="99acres", title="1 BHK Pallavaram",
            address="Foo St, Pallavaram", price=12200,
            url="https://9/2", lat=12.974, lng=80.143, furnishing="semi-furnished")


def test_same_unit_same_fingerprint():
    assert fingerprint(A) == fingerprint(B)


def test_merge_prefers_nobroker_url_order():
    nb = A.model_copy(update={"source": "nobroker", "id": "nb_3"})
    merged = merge([A, nb])
    assert merged.source == "nobroker"
    assert set(merged.also_seen_on) >= {"https://s/1"}


def test_no_latlng_falls_back_to_address():
    a = A.model_copy(update={"lat": None, "lng": None})
    b = B.model_copy(update={"lat": None, "lng": None,
                             "address": "123 Foo Street Pallavaram Chennai"})
    assert fingerprint(a) == fingerprint(b)


def test_merge_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        merge([])

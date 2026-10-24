import pytest
from src.models import Listing
from src.pipeline.enrich import (
    passes_distance_filter, passes_property_filter,
)


def _make(**kw) -> Listing:
    base = dict(id="x", source="sulekha", title="1 BHK",
                address="Pallavaram, Chennai", price=10000,
                url="https://x.test/1", lat=12.97, lng=80.18)
    base.update(kw)
    return Listing(**base)


def test_property_filter_drops_out_of_budget():
    from config import MAX_RENT
    assert passes_property_filter(_make(price=MAX_RENT - 1))
    assert not passes_property_filter(_make(price=MAX_RENT + 1))


def test_property_filter_drops_families_only_for_solo(monkeypatch):
    import config
    monkeypatch.setattr(config, "NUM_PEOPLE", 1)
    assert not passes_property_filter(_make(title="Family only 1 BHK flat"))
    assert passes_property_filter(_make(title="1 BHK flat"))


def test_distance_filter_drops_without_coords():
    ok, dist = passes_distance_filter(_make(lat=None, lng=None),
                                      office_lat=12.97, office_lng=80.18,
                                      max_km=10)
    assert ok is False and dist is None


def test_distance_filter_drops_far_away():
    ok, dist = passes_distance_filter(_make(lat=20.0, lng=80.0),
                                      office_lat=12.97, office_lng=80.18,
                                      max_km=10)
    assert ok is False
    assert dist is not None and dist > 10


def test_distance_filter_keeps_within_radius():
    ok, dist = passes_distance_filter(_make(lat=12.97, lng=80.18),
                                      office_lat=12.97, office_lng=80.18,
                                      max_km=10)
    assert ok is True
    assert dist == pytest.approx(0.0, abs=0.01)

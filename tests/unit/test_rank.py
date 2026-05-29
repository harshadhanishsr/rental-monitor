import time
from src.models import Listing
from src.pipeline.rank import fit_score

L = Listing(id="x", source="sulekha", title="1BHK",
            address="Pallikaranai, Chennai", price=10000, url="https://x",
            lat=12.97, lng=80.20)


def test_score_in_range():
    score = fit_score(L, travel_min=25, first_seen_ts=int(time.time()),
                      now_ts=int(time.time()), confirm_count=1,
                      priority=True, max_rent=15000, min_rent=3000)
    assert 0 <= score <= 100


def test_priority_locality_bumps_score():
    base = fit_score(L, travel_min=25, first_seen_ts=int(time.time()),
                     now_ts=int(time.time()), confirm_count=1, priority=False,
                     max_rent=15000, min_rent=3000)
    boost = fit_score(L, travel_min=25, first_seen_ts=int(time.time()),
                      now_ts=int(time.time()), confirm_count=1, priority=True,
                      max_rent=15000, min_rent=3000)
    assert boost - base == 15

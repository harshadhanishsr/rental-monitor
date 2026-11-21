import time
from src.models import Listing
from src.pipeline.rank import fit_score, DAY

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


def test_travel_min_none_zeros_commute_component():
    # priority=False, far past freshness window so freshness=0; min_rent==max_rent so price=0
    score = fit_score(L, travel_min=None, first_seen_ts=0,
                      now_ts=10 * DAY, confirm_count=0,
                      priority=False, max_rent=10000, min_rent=10000)
    assert score == 0


def test_confirm_count_zero_does_not_underflow():
    score = fit_score(L, travel_min=None, first_seen_ts=0,
                      now_ts=10 * DAY, confirm_count=0,
                      priority=False, max_rent=10000, min_rent=10000)
    assert score >= 0  # already guaranteed by test above, but documents the guard


def test_max_rent_equals_min_rent_does_not_div_by_zero():
    score = fit_score(L, travel_min=0, first_seen_ts=0,
                      now_ts=10 * DAY, confirm_count=0,
                      priority=False, max_rent=10000, min_rent=10000)
    # commute=40 (travel=0), price=0 (price_span guarded → ratio=0), locality=0,
    # freshness=0 (age>7d), confirm=0 → total 40
    assert score == 40


def test_freshness_exhausts_after_seven_days():
    fresh = fit_score(L, travel_min=None, first_seen_ts=10 * DAY,
                      now_ts=10 * DAY, confirm_count=0,
                      priority=False, max_rent=15000, min_rent=3000)
    stale = fit_score(L, travel_min=None, first_seen_ts=0,
                      now_ts=10 * DAY, confirm_count=0,
                      priority=False, max_rent=15000, min_rent=3000)
    assert fresh - stale == 10  # freshness component max


def test_price_above_max_rent_clamps_to_zero():
    # listing at 10000 but max_rent=8000 → over budget; price term should be 0
    # use stale listings (age>7d) so freshness=0 and price is the only variable
    score_under = fit_score(L, travel_min=None, first_seen_ts=0,
                            now_ts=10 * DAY, confirm_count=0,
                            priority=False, max_rent=12000, min_rent=3000)
    score_over = fit_score(L, travel_min=None, first_seen_ts=0,
                           now_ts=10 * DAY, confirm_count=0,
                           priority=False, max_rent=8000, min_rent=3000)
    # under budget gets >0 price term, over budget clamps to 0
    assert score_under > 0
    assert score_over == 0

from src.models import Listing

DAY = 86400


def fit_score(l: Listing, *, travel_min: float | None, first_seen_ts: int,
              now_ts: int, confirm_count: int, priority: bool,
              max_rent: int, min_rent: int) -> int:
    if travel_min is not None:
        commute = 40 * max(0.0, 1 - travel_min / 60)
    else:
        commute = 0.0
    price_span = max_rent - min_rent or 1
    price = 25 * max(0.0, (max_rent - l.price) / price_span)
    locality = 15 if priority else 0
    age_days = max(0, (now_ts - first_seen_ts) / DAY)
    freshness = 10 * max(0.0, 1 - age_days / 7)
    confirm = min(10, max(0, confirm_count - 1) * 5)
    return int(round(commute + price + locality + freshness + confirm))

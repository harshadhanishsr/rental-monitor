from src.models import Listing

DAY = 86400


def fit_score(l: Listing, *, travel_min: float | None, first_seen_ts: int,
              now_ts: int, confirm_count: int, priority: bool,
              max_rent: int, min_rent: int) -> int:
    """Return a deterministic ranking score in the range 0–100.

    Component weights and caps:
      commute   40  — linear decay 0–60 min; zero past 60 min or if travel_min is None
      price     25  — linear over [min_rent, max_rent]; guarded for max_rent == min_rent
      locality  15  — binary: +15 when listing is in a priority area
      freshness 10  — linear decay over 7 days from first_seen_ts
      confirm   10  — +5 per confirmation beyond the first, capped at 10

    Total at peak = 100. Negatives are clamped to 0.
    """
    if travel_min is not None:
        commute = 40 * max(0.0, 1 - travel_min / 60)
    else:
        commute = 0.0
    price_span = (max_rent - min_rent) or 1
    price = 25 * max(0.0, (max_rent - l.price) / price_span)
    locality = 15 if priority else 0
    age_days = max(0, (now_ts - first_seen_ts) / DAY)
    freshness = 10 * max(0.0, 1 - age_days / 7)
    confirm = min(10, max(0, confirm_count - 1) * 5)
    return int(round(commute + price + locality + freshness + confirm))

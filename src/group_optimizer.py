"""
Group house-hunting optimizer.

Given N people with N different office locations, finds the geographical
point that minimises total commute burden across the group (geometric median),
then scores and ranks listings by fairness to all members.
"""
import logging
from dataclasses import dataclass
from haversine import haversine, Unit

logger = logging.getLogger(__name__)


@dataclass
class MemberCommute:
    name: str
    office_lat: float
    office_lng: float
    distance_km: float | None = None


@dataclass
class GroupScore:
    """Commute breakdown for a single listing, for the whole group."""
    members: list[MemberCommute]
    avg_km: float
    max_km: float
    min_km: float
    fairness_score: float  # lower = better (minimise max + variance)

    @property
    def worst_commuter(self) -> MemberCommute:
        return max(self.members, key=lambda m: m.distance_km or 0)

    @property
    def best_commuter(self) -> MemberCommute:
        return min(self.members, key=lambda m: m.distance_km or 0)


def geometric_median(
    points: list[tuple[float, float]],
    max_iter: int = 200,
    tol: float = 1e-7,
) -> tuple[float, float]:
    """
    Weiszfeld algorithm: finds the point minimising sum of distances to all offices.
    Better than a simple centroid — robust to outliers, no one office dominates.
    """
    if len(points) == 1:
        return points[0]

    # Start from centroid
    lat = sum(p[0] for p in points) / len(points)
    lng = sum(p[1] for p in points) / len(points)

    for _ in range(max_iter):
        weights = []
        for p in points:
            d = haversine((lat, lng), p, unit=Unit.KILOMETERS)
            weights.append(1.0 / max(d, 0.01))  # avoid div-by-zero

        total_w = sum(weights)
        new_lat = sum(w * p[0] for w, p in zip(weights, points)) / total_w
        new_lng = sum(w * p[1] for w, p in zip(weights, points)) / total_w

        if abs(new_lat - lat) < tol and abs(new_lng - lng) < tol:
            break
        lat, lng = new_lat, new_lng

    return lat, lng


def optimal_search_centre(members: list[dict]) -> tuple[float, float]:
    """Return the geometric median of all members' office locations."""
    points = [(m["office_lat"], m["office_lng"]) for m in members]
    centre = geometric_median(points)
    logger.info(
        "Group optimal centre: (%.4f, %.4f) from %d offices",
        centre[0], centre[1], len(points),
    )
    return centre


def score_listing_for_group(
    listing_lat: float,
    listing_lng: float,
    members: list[dict],
) -> GroupScore:
    """
    Calculate per-member commute distances and a fairness score for a listing.

    Fairness score (lower = better):
        max_commute + 0.5 × std_deviation
    This penalises both long worst-case commutes and inequitable splits.
    """
    commutes = []
    for m in members:
        d = haversine(
            (m["office_lat"], m["office_lng"]),
            (listing_lat, listing_lng),
            unit=Unit.KILOMETERS,
        )
        commutes.append(MemberCommute(
            name=m["name"],
            office_lat=m["office_lat"],
            office_lng=m["office_lng"],
            distance_km=round(d, 2),
        ))

    distances = [c.distance_km for c in commutes]
    avg_km = sum(distances) / len(distances)
    max_km = max(distances)
    min_km = min(distances)

    variance = sum((d - avg_km) ** 2 for d in distances) / len(distances)
    std_dev = variance ** 0.5

    fairness_score = max_km + 0.5 * std_dev

    return GroupScore(
        members=commutes,
        avg_km=round(avg_km, 2),
        max_km=round(max_km, 2),
        min_km=round(min_km, 2),
        fairness_score=round(fairness_score, 3),
    )


def passes_group_filter(score: GroupScore, max_per_person_km: float) -> bool:
    """Reject the listing if any member's commute exceeds the per-person limit."""
    return all(
        (m.distance_km or 0) <= max_per_person_km
        for m in score.members
    )


def format_group_commutes(score: GroupScore) -> str:
    """Format per-member commute lines for Telegram alerts."""
    lines = ["👥 *Commute distances:*"]
    for m in score.members:
        d = m.distance_km
        bar = "🟢" if d <= 5 else "🟡" if d <= 10 else "🔴"
        lines.append(f"  {bar} {m.name}: {d:.1f} km")
    lines.append(
        f"  📊 Avg: {score.avg_km:.1f} km | Max: {score.max_km:.1f} km"
    )
    return "\n".join(lines)

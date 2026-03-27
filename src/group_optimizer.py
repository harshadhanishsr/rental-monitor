"""
Group house-hunting optimizer.

Given N people with N different office locations and transport modes,
finds the geographical point that minimises total commute burden, then
scores and ranks listings by fairness to all members.

Scoring is based on TRAVEL TIME (minutes), not straight-line distance.
Uses Google Maps Distance Matrix API when available; falls back to a
speed heuristic (mode-aware) otherwise.
"""
import logging
import sqlite3
from dataclasses import dataclass
from haversine import haversine, Unit
from src.travel_time import get_travel_time

logger = logging.getLogger(__name__)


@dataclass
class MemberCommute:
    name: str
    office_lat: float
    office_lng: float
    transport: str
    distance_km: float | None = None
    travel_minutes: float | None = None
    time_source: str = "heuristic"   # "gmaps" | "heuristic" | "cached"

    @property
    def display(self) -> str:
        """Short label for alerts, e.g. '24 min (transit)' or '6.2 km'."""
        if self.travel_minutes is not None:
            indicator = "~" if self.time_source == "heuristic" else ""
            return f"{indicator}{self.travel_minutes:.0f} min ({self.transport})"
        return f"{self.distance_km:.1f} km"


@dataclass
class GroupScore:
    """Commute breakdown for a single listing across all group members."""
    members: list[MemberCommute]

    # Time-based metrics (minutes) — primary ranking signal
    avg_minutes: float
    max_minutes: float
    min_minutes: float
    fairness_score: float   # lower = better

    # Distance fallback (km)
    avg_km: float
    max_km: float

    @property
    def worst_commuter(self) -> MemberCommute:
        return max(self.members, key=lambda m: m.travel_minutes or m.distance_km or 0)

    @property
    def best_commuter(self) -> MemberCommute:
        return min(self.members, key=lambda m: m.travel_minutes or m.distance_km or 0)


def geometric_median(
    points: list[tuple[float, float]],
    max_iter: int = 200,
    tol: float = 1e-7,
) -> tuple[float, float]:
    """
    Weiszfeld algorithm: point minimising sum of distances to all office locations.
    Better than a centroid — robust to outliers.
    """
    if len(points) == 1:
        return points[0]

    lat = sum(p[0] for p in points) / len(points)
    lng = sum(p[1] for p in points) / len(points)

    for _ in range(max_iter):
        weights = [
            1.0 / max(haversine((lat, lng), p, unit=Unit.KILOMETERS), 0.01)
            for p in points
        ]
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
    conn: sqlite3.Connection,
) -> GroupScore:
    """
    Calculate per-member commute times and a fairness score for one listing.

    Fairness score (lower = better):
        max_commute_minutes + 0.5 × std_deviation_minutes
    Penalises both the worst-case commute and inequity between members.
    Falls back to km-based scoring if travel time is unavailable.
    """
    commutes = []
    for m in members:
        mode = m.get("transport", "driving")
        dist_km = round(haversine(
            (m["office_lat"], m["office_lng"]),
            (listing_lat, listing_lng),
            unit=Unit.KILOMETERS,
        ), 2)

        minutes, source = get_travel_time(
            listing_lat, listing_lng,
            m["office_lat"], m["office_lng"],
            mode, conn,
        )

        commutes.append(MemberCommute(
            name=m["name"],
            office_lat=m["office_lat"],
            office_lng=m["office_lng"],
            transport=mode,
            distance_km=dist_km,
            travel_minutes=round(minutes, 1),
            time_source=source,
        ))

    times = [c.travel_minutes for c in commutes]
    avg_min = sum(times) / len(times)
    max_min = max(times)
    min_min = min(times)

    variance = sum((t - avg_min) ** 2 for t in times) / len(times)
    fairness_score = max_min + 0.5 * (variance ** 0.5)

    dists = [c.distance_km for c in commutes]

    return GroupScore(
        members=commutes,
        avg_minutes=round(avg_min, 1),
        max_minutes=round(max_min, 1),
        min_minutes=round(min_min, 1),
        fairness_score=round(fairness_score, 2),
        avg_km=round(sum(dists) / len(dists), 2),
        max_km=round(max(dists), 2),
    )


def passes_group_filter(
    score: GroupScore,
    max_minutes: float,
    max_km: float,
) -> bool:
    """
    Reject if any member exceeds the per-person commute limit.
    Uses minutes if available, falls back to km.
    """
    for m in score.members:
        if m.travel_minutes is not None and m.travel_minutes > max_minutes:
            return False
        if m.travel_minutes is None and (m.distance_km or 0) > max_km:
            return False
    return True


def format_group_commutes(score: GroupScore) -> str:
    """Format per-member commute lines for Telegram alerts."""
    lines = ["👥 *Commute times:*"]
    for m in score.members:
        mins = m.travel_minutes
        if mins is not None:
            bar = "🟢" if mins <= 20 else "🟡" if mins <= 40 else "🔴"
            est = "~" if m.time_source == "heuristic" else ""
            lines.append(f"  {bar} {m.name}: {est}{mins:.0f} min ({m.transport})")
        else:
            d = m.distance_km or 0
            bar = "🟢" if d <= 5 else "🟡" if d <= 10 else "🔴"
            lines.append(f"  {bar} {m.name}: {d:.1f} km ({m.transport})")

    lines.append(
        f"  📊 Avg: {score.avg_minutes:.0f} min | Worst: {score.max_minutes:.0f} min"
    )
    return "\n".join(lines)

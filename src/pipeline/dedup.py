from __future__ import annotations
import hashlib
import re
from src.models import Listing

SOURCE_RANK = {
    "nobroker": 0, "sulekha": 1, "99acres": 2, "housing": 3,
    "magicbricks": 4, "squareyards": 5, "commonfloor": 6,
    "olx": 7, "duckduckgo": 8,
}

_GEOHASH_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"

# Abbreviation expansions applied before address normalisation
_ADDR_ABBREVS = [
    (r"\bst\b",     "street"),
    (r"\brd\b",     "road"),
    (r"\bave?\b",   "avenue"),
    (r"\bnr\b",     "near"),
    (r"\bopp\b",    "opposite"),
    (r"\bextn\b",   "extension"),
    (r"\bext\b",    "extension"),
    (r"\bph\b",     "phase"),
    (r"\bblk\b",    "block"),
    (r"\bsoc\b",    "society"),
]


def geohash(lat: float, lng: float, precision: int = 7) -> str:
    lat_lo, lat_hi = -90.0, 90.0
    lng_lo, lng_hi = -180.0, 180.0
    bits, hash_chars, ch_bits, even = [], [], 0, True
    while len(hash_chars) < precision:
        if even:
            mid = (lng_lo + lng_hi) / 2
            bit = 1 if lng > mid else 0
            (lng_lo, lng_hi) = (mid, lng_hi) if bit else (lng_lo, mid)
        else:
            mid = (lat_lo + lat_hi) / 2
            bit = 1 if lat > mid else 0
            (lat_lo, lat_hi) = (mid, lat_hi) if bit else (lat_lo, mid)
        bits.append(bit)
        ch_bits += 1
        even = not even
        if ch_bits == 5:
            idx = bits[-5] * 16 + bits[-4] * 8 + bits[-3] * 4 + bits[-2] * 2 + bits[-1]
            hash_chars.append(_GEOHASH_B32[idx])
            ch_bits = 0
    return "".join(hash_chars)


def _norm_addr(addr: str) -> str:
    s = addr.lower()
    s = re.sub(r"\d+[a-z]?[/-]?\d*", " ", s)  # strip building numbers
    for pattern, replacement in _ADDR_ABBREVS:
        s = re.sub(pattern, replacement, s)
    s = re.sub(r"[^a-z\s]", " ", s)          # strip remaining non-alpha
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _bedrooms(title: str) -> int:
    m = re.search(r"(\d)\s*(bhk|rk)", title.lower())
    return int(m.group(1)) if m else 1


def _furn_canon(f: str) -> str:
    f = (f or "unknown").lower()
    if "unfurn" in f: return "unfurnished"
    if "semi" in f:   return "semi"
    if "furn" in f:   return "furnished"
    return "unknown"


def fingerprint(l: Listing) -> str:
    if l.lat is not None and l.lng is not None:
        loc = geohash(l.lat, l.lng, 7)
    else:
        loc = _norm_addr(l.address)
    price_bucket = round(l.price / 500) * 500
    key = f"{loc}_{price_bucket}_{_bedrooms(l.title)}_{_furn_canon(l.furnishing)}"
    return hashlib.sha1(key.encode()).hexdigest()


def merge(listings: list[Listing]) -> Listing:
    if not listings:
        raise ValueError("merge() requires at least one listing")
    best = sorted(listings, key=lambda x: SOURCE_RANK.get(x.source, 99))[0]
    others = [l for l in listings if l.id != best.id]
    return best.model_copy(update={
        "also_seen_on": sorted({l.url for l in others}),
        "lat": best.lat or next((l.lat for l in listings if l.lat), None),
        "lng": best.lng or next((l.lng for l in listings if l.lng), None),
        "rating": max((l.rating for l in listings if l.rating is not None), default=None),
        "fingerprint": fingerprint(best),
    })

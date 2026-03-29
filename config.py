"""
=================================================================
  RENTAL MONITOR — USER CONFIGURATION
  Edit this file to personalise your search.
  All scraper queries, filters, and alerts are driven from here.
=================================================================
"""

# ── REFERENCE LOCATION ───────────────────────────────────────
# Your office / workplace / any point you want proximity to.
# Find coordinates: https://maps.google.com → right-click → "What's here?"
import os as _os
from dotenv import load_dotenv as _load_dotenv
_load_dotenv()

# Reads from .env if set, otherwise falls back to example coords below.
# Set OFFICE_LAT / OFFICE_LNG in your .env to keep your real location private.
OFFICE_LAT = float(_os.environ.get("OFFICE_LAT", "13.0827"))   # example: Chennai city centre
OFFICE_LNG = float(_os.environ.get("OFFICE_LNG", "80.2707"))

# ── CITY & AREAS ─────────────────────────────────────────────
CITY = "Chennai"   # City name (used in scraper search queries)

# Localities to actively search. Scrapers will target each of these.
SEARCH_AREAS = [
    # Areas between Chromepet and Sholinganallur — the sweet spot for both offices
    "Pallikaranai",
    "Medavakkam",
    "Keelkattalai",
    "Nanganallur",
    "Adambakkam",
    "Perumbakkam",
    "Sholinganallur",
    "Ullagaram",
    "Chromepet",
    "Pallavaram",
]

PRIORITY_LOCALITIES = {
    "pallikaranai", "medavakkam", "keelkattalai", "nanganallur",
    "adambakkam", "perumbakkam", "ullagaram", "chromepet",
    "pallavaram", "sholinganallur", "puzhuthivakkam",
}

# ── SEARCH RADIUS ─────────────────────────────────────────────
# Only listings within this distance from OFFICE_LAT/LNG are alerted.
MAX_RADIUS_KM = 10.0

# Zone thresholds (km) — used in alert messages
ZONE_SUPER_CLOSE_KM = 2.0    # ≤ this → "SUPER CLOSE"
ZONE_PREFERRED_KM   = 5.0    # ≤ this → "PREFERRED"
ZONE_NEARBY_KM      = 8.0    # ≤ this → "NEARBY"
# ACCEPTABLE = up to MAX_RADIUS_KM

# Show listings beyond MAX_RADIUS only if they meet both conditions below
FAR_MAX_PRICE  = 10_000   # price must be ≤ this (₹)
FAR_MIN_RATING = 4.0      # rating must be ≥ this (if platform provides one)

# ── PROPERTY TYPE ─────────────────────────────────────────────
# What are you looking for?
# Supported values: "1rk"  "1bhk"  "2bhk"  "3bhk"  "studio"
PROPERTY_TYPE = "1bhk"

# Number of people sharing the flat
# 1 → bachelor-friendly listings preferred
# 2+ → family listings included
NUM_PEOPLE = 1

# Furnishing: "any"  |  "furnished"  |  "semi-furnished"  |  "unfurnished"
FURNISHING = "any"

# ── BUDGET ───────────────────────────────────────────────────
MIN_RENT =  3_000   # ₹/month  — skip listings below this (likely fake/deposit)
MAX_RENT = 15_000   # ₹/month  — skip listings above this

# ── SCHEDULER ────────────────────────────────────────────────
# How often to scan for new listings (seconds).
# 3600 = every hour  |  7200 = every 2 hours
CHECK_INTERVAL_SECONDS = 3600

# ── GROUP MODE ───────────────────────────────────────────────
# Multiple people looking for a place together, each with a different workplace?
# Set GROUP_MODE = True and fill in GROUP_MEMBERS below.
# The system will find the geographically fairest location for the whole group
# and show each person's individual commute distance in every alert.
#
# When GROUP_MODE is True, OFFICE_LAT/OFFICE_LNG above are IGNORED —
# the optimal search centre is automatically calculated from GROUP_MEMBERS.

GROUP_MODE = False   # Solo search for Harsha only

GROUP_MEMBERS = [
    {
        "name":       "Harsha",
        "office_lat": 12.9698,   # Blackstraw AI, Chromepet
        "office_lng": 80.1409,
        "transport":  "transit",
    },
    {
        "name":       "Daddy",
        "office_lat": 12.9010,   # Wipro, Sholinganallur ELCOT SEZ
        "office_lng": 80.2278,
        "transport":  "transit",
    },
]

# Maximum commute time each member is willing to accept (minutes).
# Listings where ANY member would exceed this are filtered out.
# Used when travel time is available (Google Maps API key set).
MAX_COMMUTE_PER_PERSON_MINUTES = 50

# Fallback when no API key: maximum straight-line distance per person (km)
MAX_COMMUTE_PER_PERSON_KM = 15.0

# ── GOOGLE MAPS API (optional but recommended for group mode) ─
# Without this, travel times are estimated from straight-line distance.
# Get a free API key: https://console.cloud.google.com → Enable "Distance Matrix API"
# Free tier: 40,000 elements/month (enough for daily use)
# Set in .env:  GOOGLE_MAPS_API_KEY=AIza...
GOOGLE_MAPS_API_KEY = ""  # leave blank — read from .env at runtime

# ── NOTIFICATIONS ─────────────────────────────────────────────
# Keep secrets in .env — not here.
# Telegram (free, recommended):
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_CHAT_ID=...
# WhatsApp via Twilio (fallback):
#   TWILIO_ACCOUNT_SID=...   TWILIO_AUTH_TOKEN=...
#   TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
#   WHATSAPP_TO=whatsapp:+91XXXXXXXXXX

# ─────────────────────────────────────────────────────────────
# Internal helpers — no need to edit below this line
# ─────────────────────────────────────────────────────────────
import re as _re

def _parse_property_type(pt: str) -> dict:
    pt = pt.lower().strip()
    m = _re.match(r"(\d)(bhk|rk|rk\+?|studio)", pt)
    if m:
        beds = int(m.group(1))
        kind = m.group(2)
    elif pt == "studio":
        beds, kind = 1, "rk"
    else:
        beds, kind = 1, "bhk"
    label = f"{beds} {'BHK' if kind == 'bhk' else 'RK'}"
    slug  = f"{beds}{kind}"     # "1bhk", "2bhk", "1rk"
    return {"beds": beds, "kind": kind, "label": label, "slug": slug}

_PT            = _parse_property_type(PROPERTY_TYPE)
BEDROOMS       = _PT["beds"]    # int: 1, 2, 3 …
IS_RK          = _PT["kind"] == "rk"
PROPERTY_LABEL = _PT["label"]   # "1 BHK", "2 BHK", "1 RK" …
PROPERTY_SLUG  = _PT["slug"]    # "1bhk", "2bhk", "1rk" …

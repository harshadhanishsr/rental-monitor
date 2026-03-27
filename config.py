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
OFFICE_LAT = 13.0827   # latitude  (example: Chennai city centre — change to your location)
OFFICE_LNG = 80.2707   # longitude (right-click on Google Maps → "What's here?" to get yours)

# ── CITY & AREAS ─────────────────────────────────────────────
CITY = "Chennai"   # City name (used in scraper search queries)

# Localities to actively search. Scrapers will target each of these.
SEARCH_AREAS = [
    "Chromepet",
    "Pallavaram",
    "Tambaram",
    "Nanganallur",
    "Pammal",
    "Selaiyur",
]

# Areas that are especially convenient for you — listed first in alerts
# and marked with ⭐. Add any locality you'd prefer to live near.
PRIORITY_LOCALITIES = {
    "chromepet", "pallavaram", "nanganallur", "pammal", "selaiyur",
    "st. thomas mount", "meenambakkam", "tirusulam", "alandur",
    "kilkattalai", "perungalathur", "mudichur", "tambaram",
    "ullagaram", "puzhuthivakkam", "medavakkam",
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

import re
from src.models import Listing
from config import MAX_RENT, MIN_RENT, NUM_PEOPLE, FURNISHING

_FAMILIES_ONLY = re.compile(r"famil(y|ies)\s*only", re.IGNORECASE)
_BACHELOR_KEYWORDS = re.compile(r"\b(bachelor|single|bachelors)\b", re.IGNORECASE)
_FURNISHED_RE = re.compile(r"\b(furnished|semi.furnished|unfurnished)\b", re.IGNORECASE)


def passes_property_filter(listing: Listing) -> bool:
    # Budget
    if listing.price > MAX_RENT:
        return False
    if listing.price < MIN_RENT:
        return False

    # Family-only listings are skipped if searching solo / as bachelors
    if _FAMILIES_ONLY.search(listing.title):
        if NUM_PEOPLE < 3:
            return False

    # Bachelor filter
    if listing.bachelors_allowed is None:
        if _BACHELOR_KEYWORDS.search(listing.title):
            listing.bachelors_allowed = True
    if NUM_PEOPLE == 1 and listing.bachelors_allowed is False:
        return False

    # Furnishing preference
    if FURNISHING != "any":
        text = (listing.title + " " + (listing.furnishing or "")).lower()
        if FURNISHING == "furnished" and "furnished" not in text:
            return False
        if FURNISHING == "semi-furnished" and "semi" not in text:
            return False
        if FURNISHING == "unfurnished" and "unfurnished" not in text:
            return False

    return True

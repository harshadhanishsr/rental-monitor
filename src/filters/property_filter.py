import re
from src.models import Listing

_FAMILIES_ONLY = re.compile(r"famil(y|ies)\s*only", re.IGNORECASE)
_BACHELOR_KEYWORDS = re.compile(r"\b(bachelor|single|bachelors)\b", re.IGNORECASE)

MAX_PRICE = 15_000


def passes_property_filter(listing: Listing) -> bool:
    if listing.price > MAX_PRICE:
        return False
    # Scrapers already filter by bedroom=1 at the source — no title check needed
    if _FAMILIES_ONLY.search(listing.title):
        return False
    # If platform didn't expose bachelors_allowed, infer from title/description
    if listing.bachelors_allowed is None:
        if _BACHELOR_KEYWORDS.search(listing.title):
            listing.bachelors_allowed = True
    if listing.bachelors_allowed is False:
        return False
    return True

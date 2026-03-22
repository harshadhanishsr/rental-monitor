# tests/test_models.py
import json
from src.models import Listing

def test_listing_defaults():
    listing = Listing(
        id="123",
        source="nobroker",
        title="1 BHK in Chromepet",
        address="Chromepet, Chennai",
        price=12000,
        url="https://nobroker.in/property/123",
    )
    assert listing.furnishing == "unknown"
    assert listing.bachelors_allowed is None
    assert listing.rating is None
    assert listing.review_snippet is None
    assert listing.images == []
    assert listing.lat is None
    assert listing.lng is None

def test_listing_to_json_roundtrip():
    listing = Listing(
        id="456",
        source="olx",
        title="1BHK flat",
        address="Mimillichery",
        price=10000,
        url="https://olx.in/item/456",
        furnishing="furnished",
        bachelors_allowed=True,
        rating=4.2,
        review_snippet="Great place",
        images=["https://img1.jpg", "https://img2.jpg"],
        lat=12.97,
        lng=80.14,
    )
    data = json.loads(listing.to_json())
    assert data["id"] == "456"
    assert data["price"] == 10000
    assert data["images"] == ["https://img1.jpg", "https://img2.jpg"]

def test_listing_from_json():
    original = Listing(
        id="789", source="magicbricks", title="BHK",
        address="Chromepet", price=13500, url="https://mb.com/789",
    )
    restored = Listing.from_json(original.to_json())
    assert restored.id == "789"
    assert restored.price == 13500

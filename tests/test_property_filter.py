import pytest
from src.models import Listing
from src.filters.property_filter import passes_property_filter


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK in Chromepet",
                    address="Chromepet", price=12000, url="http://x.com")
    return Listing(**{**defaults, **kwargs})


def test_valid_listing_passes():
    assert passes_property_filter(make_listing()) is True

def test_price_at_limit_passes():
    assert passes_property_filter(make_listing(price=15000)) is True

def test_price_over_limit_fails():
    assert passes_property_filter(make_listing(price=15001)) is False

def test_non_1bhk_title_fails():
    assert passes_property_filter(make_listing(title="2 BHK in Chromepet")) is False

def test_1bhk_lowercase_passes():
    assert passes_property_filter(make_listing(title="spacious 1bhk flat")) is True

def test_bachelors_none_passes():
    assert passes_property_filter(make_listing(bachelors_allowed=None)) is True

def test_bachelors_true_passes():
    assert passes_property_filter(make_listing(bachelors_allowed=True)) is True

def test_bachelors_false_fails():
    assert passes_property_filter(make_listing(bachelors_allowed=False)) is False

def test_families_only_keyword_in_title_fails():
    assert passes_property_filter(make_listing(title="1 BHK families only")) is False

def test_bachelor_keyword_in_title_sets_allowed():
    listing = make_listing(title="1 BHK bachelor friendly", bachelors_allowed=None)
    assert passes_property_filter(listing) is True

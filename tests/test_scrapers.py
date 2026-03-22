from src.scrapers.nobroker import extract_id as nb_extract_id, parse_price as nb_parse_price
from src.scrapers.magicbricks import extract_id as mb_extract_id
from src.scrapers.acres99 import extract_id as ac_extract_id
from src.scrapers.olx import extract_id as olx_extract_id
from src.scrapers.housing import extract_id as hc_extract_id
from src.scrapers.quikr import extract_id as qk_extract_id

# NoBroker
def test_nobroker_extract_id():
    assert nb_extract_id("https://www.nobroker.in/property/rental/chennai/12345678") == "12345678"

def test_nobroker_parse_price_with_comma():
    assert nb_parse_price("₹12,500 / month") == 12500

def test_nobroker_parse_price_plain():
    assert nb_parse_price("15000") == 15000

def test_nobroker_parse_price_none_on_invalid():
    assert nb_parse_price("Contact owner") is None

# MagicBricks
def test_magicbricks_extract_id_from_path():
    assert mb_extract_id("https://www.magicbricks.com/property-for-rent/1-BHK/PRO12345") == "PRO12345"

def test_magicbricks_extract_id_from_query():
    assert mb_extract_id("https://www.magicbricks.com/msite/propertyDetails?propertyId=67890") == "67890"

# 99acres
def test_99acres_extract_id():
    assert ac_extract_id("https://www.99acres.com/1-bhk-flat-for-rent-in-chromepet-chennai-ffid-E7654321-1") == "E7654321"

def test_99acres_extract_id_numeric():
    assert ac_extract_id("https://www.99acres.com/property/12345") == "12345"

# OLX
def test_olx_extract_id():
    assert olx_extract_id("https://www.olx.in/item/1-bhk-chromepet-ID1234567890.html") == "1234567890"

def test_olx_extract_id_path():
    assert olx_extract_id("https://www.olx.in/item/flat-ID9876543210.html") == "9876543210"

# Housing.com
def test_housing_extract_id():
    assert hc_extract_id("https://housing.com/in/rent/properties/chennai/chromepet/abc-def-123456") == "abc-def-123456"

# Quikr
def test_quikr_extract_id_numeric():
    assert qk_extract_id("https://www.quikr.com/homes/1-bhk-flat-for-rent/chromepet/12345678") == "12345678"

def test_quikr_extract_id_slug_with_numeric_suffix():
    assert qk_extract_id("https://www.quikr.com/homes/flat-for-rent-87654321") == "87654321"

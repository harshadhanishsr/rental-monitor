"""Adapters must respect config.CITY — not hardcode Chennai."""
import importlib

import pytest


@pytest.fixture
def reload_config():
    """Patch config constants then reload modules that read them at import time."""
    import config
    original = {
        "CITY": config.CITY,
        "SEARCH_AREAS": list(config.SEARCH_AREAS),
        "PROPERTY_SLUG": config.PROPERTY_SLUG,
    }

    def _apply(city: str, areas: list[str]):
        config.CITY = city
        config.SEARCH_AREAS = areas
        return config

    yield _apply

    config.CITY = original["CITY"]
    config.SEARCH_AREAS = original["SEARCH_AREAS"]
    config.PROPERTY_SLUG = original["PROPERTY_SLUG"]


# ─── MagicBricks ──────────────────────────────────────────────────

def test_magicbricks_url_uses_configured_city(reload_config):
    reload_config(city="Bangalore", areas=["Koramangala", "HSR Layout"])
    from src.sources.magicbricks import MagicBricks
    urls = MagicBricks()._urls(None)
    assert len(urls) == 2
    assert all("-bangalore-pppfr" in u for u in urls)
    assert "koramangala" in urls[0]
    assert "hsr-layout" in urls[1]
    assert "-chennai-" not in urls[0]


def test_magicbricks_url_chennai_unchanged(reload_config):
    reload_config(city="Chennai", areas=["Pallavaram"])
    from src.sources.magicbricks import MagicBricks
    urls = MagicBricks()._urls(None)
    assert urls == [
        "https://www.magicbricks.com/1-bhk-flats-for-rent-in-pallavaram-chennai-pppfr"
    ]


# ─── 99acres ──────────────────────────────────────────────────────

def test_99acres_url_chennai(reload_config):
    reload_config(city="Chennai", areas=["Pallavaram"])
    from src.sources.ninetynine_acres import NinetyNineAcres
    urls = NinetyNineAcres()._urls(None)
    assert len(urls) == 1
    assert "/chennai?" in urls[0]
    assert "city=32" in urls[0]


def test_99acres_url_bangalore(reload_config):
    reload_config(city="Bangalore", areas=["Koramangala"])
    from src.sources.ninetynine_acres import NinetyNineAcres
    urls = NinetyNineAcres()._urls(None)
    assert len(urls) == 1
    assert "/bangalore?" in urls[0]
    assert "city=20" in urls[0]


def test_99acres_url_multi_word_city(reload_config):
    reload_config(city="New Delhi", areas=["Saket"])
    from src.sources.ninetynine_acres import NinetyNineAcres
    urls = NinetyNineAcres()._urls(None)
    assert "/new-delhi?" in urls[0]
    assert "city=1" in urls[0]


def test_99acres_skips_unknown_city(reload_config, caplog):
    reload_config(city="Madurai", areas=["Anna Nagar"])
    from src.sources.ninetynine_acres import NinetyNineAcres
    with caplog.at_level("WARNING", logger="99acres"):
        urls = NinetyNineAcres()._urls(None)
    assert urls == []
    assert any("no 99acres city id" in r.message.lower() for r in caplog.records)


def test_99acres_env_override(reload_config, monkeypatch):
    reload_config(city="Madurai", areas=["Anna Nagar"])
    monkeypatch.setenv("NINETYNINE_ACRES_CITY_ID", "99")
    from src.sources.ninetynine_acres import NinetyNineAcres
    urls = NinetyNineAcres()._urls(None)
    assert len(urls) == 1
    assert "/madurai?" in urls[0]
    assert "city=99" in urls[0]

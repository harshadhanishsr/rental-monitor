"""Registry of working source adapters.

Adapters listed in ``ALL_SOURCES`` are wired into the engine by default. The
order here is the order in which they're scheduled; deduplication makes the
order irrelevant for output, but a stable order keeps logs readable.

Deferred (not yet wired):
    - CommonFloor — needs Playwright or undocumented XHR endpoint
    - NoBroker — needs DevTools-captured working XHR params
    - Housing.com — needs DevTools-captured search-id slug URL
"""
from __future__ import annotations
from src.sources.base import SourceAdapter
from src.sources.duckduckgo import DuckDuckGo
from src.sources.magicbricks import MagicBricks
from src.sources.ninetynine_acres import NinetyNineAcres
from src.sources.olx import OLX
from src.sources.squareyards import SquareYards
from src.sources.sulekha import Sulekha


def all_sources() -> list[SourceAdapter]:
    return [Sulekha(), SquareYards(), NinetyNineAcres(), MagicBricks(), OLX(), DuckDuckGo()]

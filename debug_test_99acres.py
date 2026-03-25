"""Quick test: run 99acres rent scraper and print found listings."""
import sys
sys.path.insert(0, '/app')
from src.scrapers.acres99 import scrape

listings = scrape()
print(f"\nFound {len(listings)} listings from 99acres\n")
for l in listings[:5]:
    print(f"  ID: {l.id}")
    print(f"  Title: {l.title}")
    print(f"  Price: ₹{l.price}/month")
    print(f"  Address: {l.address}")
    print(f"  URL: {l.url[:80]}")
    print()

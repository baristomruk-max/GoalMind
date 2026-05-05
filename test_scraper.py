import logging
from scraper import IddaaScraper
from database import Database
from ml_predictor import MLPredictor

logging.basicConfig(level=logging.INFO)
db = Database()
predictor = MLPredictor(db)
scraper = IddaaScraper(db, predictor)

print("Fetching upcoming matches...")
matches = scraper.fetch_upcoming_matches(days=3)
print(f"Matches found: {len(matches)}")
print(matches[:5] if matches else "No matches")

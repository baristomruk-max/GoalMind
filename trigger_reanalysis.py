import logging
from scraper import IddaaScraper
from database import Database
from ml_predictor import MLPredictor

# Logları ayarla
logging.basicConfig(level=logging.INFO)

db = Database()
predictor = MLPredictor(db)
scraper = IddaaScraper(db, predictor)

print("--- Triggering Weekly Re-Analysis (Phase 13 Calibration) ---")
result = scraper.get_weekly_predictions()

print(f"\nDone! Total Mapped: {result.get('total_mapped')}")
print(f"Platinum Count: {len([p for p in result.get('predictions', []) if 'PLATINUM' in p.get('prediction', '')])}")
print(f"Gold Count: {len([p for p in result.get('predictions', []) if 'GOLD' in p.get('prediction', '')])}")
print(f"Silver Count: {len([p for p in result.get('predictions', []) if 'SILVER' in p.get('prediction', '')])}")

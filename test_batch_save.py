import logging
from database import Database
import json

logging.basicConfig(level=logging.INFO)
db = Database()

mock_predictions = [{
    'id': 'test_123',
    'match_date': '2026-03-22',
    'home_team': 'Chelsea',
    'away_team': 'Arsenal',
    'predicted_result': '1',
    'confidence': 65.5,
    'goals_market': {'over_25': 60},
    'win_probabilities': {'home': 65.5, 'draw': 20, 'away': 14.5},
    'league_id': 1,
    'model_version': 'v1.2 (Test)',
    'tier': '🥇 GOLD',
    'tier_confidence': 70.0,
    'advanced_metrics': {'layers': {}}
}]

print("--- Testing save_predictions_batch ---")
try:
    db.save_predictions_batch(mock_predictions)
    print("✅ Success!")
except Exception as e:
    print(f"❌ Failed: {e}")

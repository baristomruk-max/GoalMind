import os
import logging
from database import Database
from ml_predictor import MLPredictor

# Logları ayarla
logging.basicConfig(level=logging.INFO)

db = Database()
predictor = MLPredictor(db)

# Test 1: Güçlü Ev Sahibi vs Zayıf Deplasman (Normal)
print("\n--- TEST 1: Arsenal vs Chelsea ---")
res1 = predictor.predict_match_ml("Arsenal", "Chelsea", league_id=700)
print(f"Tier: {res1.get('tier')}")
print(f"Confidence: {res1.get('confidence')}%")
print(f"Prediction: {res1.get('prediction')}")
print(f"Goals Market: {res1.get('goals_market')}")

# Test 2: Belirsiz Maç (Market Switch Check)
print("\n--- TEST 2: Low Confidence Match ---")
# Bu maçın verileri muhtemelen düşük çıkacaktır
res2 = predictor.predict_match_ml("Everton", "Liverpool", league_id=700)
print(f"Tier: {res2.get('tier')}")
print(f"Confidence: {res2.get('confidence')}%")
print(f"Goals Market: {res2.get('goals_market')}")

print("\nVerification Complete.")

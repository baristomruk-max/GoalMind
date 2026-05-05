import sys
import os
from database import Database
from ml_predictor import MLPredictor
import json

db = Database()
predictor = MLPredictor(db)

# Bazı takımlar al (Veritabanında olduğundan emin olduğumuz)
teams = db.get_teams()
if len(teams) >= 2:
    home, away = teams[0], teams[1]
    print(f"\n--- Testing Prediction: {home} vs {away} ---")
    
    result = predictor.predict_match_ml(home, away)
    
    # JSON formatında güzelce yazdır
    print(json.dumps(result, indent=4, ensure_all_chars=False))
    
    if "tier" in result:
        print(f"\n✅ SUCCESS: Tier found -> {result['tier']}")
        print(f"✅ SUCCESS: Confidence -> %{result['confidence']}")
    else:
        print("\n❌ FAILED: Tier not found in result.")
else:
    print("Not enough teams in database to test.")

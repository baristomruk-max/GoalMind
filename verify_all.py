import sqlite3
import json
from database import Database
from ml_predictor import MLPredictor

def verify():
    print("--- 1. Verifying Database Schema ---")
    conn = sqlite3.connect("football_data.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(predictions_history)")
    columns = [row[1] for row in cursor.fetchall()]
    
    required = ["tier", "tier_confidence", "advanced_metrics_json"]
    for col in required:
        if col in columns:
            print(f"✅ Column '{col}' exists.")
        else:
            print(f"❌ Column '{col}' MISSING.")
    conn.close()

    print("\n--- 2. Verifying Prediction Logic ---")
    db = Database()
    predictor = MLPredictor(db)
    teams = db.get_teams()
    if len(teams) >= 2:
        res = predictor.predict_match_ml(teams[0], teams[1])
        if "tier" in res:
            print(f"✅ Prediction Success: {res['tier']} (%{res['confidence']})")
            print(f"   Layers: {list(res['advanced_metrics']['layers'].keys())}")
        else:
            print(f"❌ Prediction Failed: {res.get('error', 'Unknown Error')}")
    else:
        print("Not enough data for prediction test.")

if __name__ == "__main__":
    verify()

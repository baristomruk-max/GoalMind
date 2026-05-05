import os
import json
import sqlite3
import logging
from database import Database
from ml_predictor import MLPredictor
from scraper import IddaaScraper

# Logları ayarla
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Phase15Fix")

db = Database()
predictor = MLPredictor(db)
scraper = IddaaScraper(db, predictor)

def run_fix():
    print("🚀 [Phase 15] Final Repair Starting...")
    conn = db.get_connection()
    
    # 1. Double-Encoding Fix
    print("🧹 Cleaning double-encoded Goals Market data...")
    cursor = conn.execute("SELECT id, goals_market FROM predictions_history")
    rows = cursor.fetchall()
    fixed_count = 0
    for row in rows:
        data = row['goals_market']
        if data and isinstance(data, str) and data.startswith('"{'):
            try:
                # Double encoded string -> decoded string -> dict
                clean_dict = json.loads(json.loads(data))
                conn.execute("UPDATE predictions_history SET goals_market = ? WHERE id = ?", (json.dumps(clean_dict), row['id']))
                fixed_count += 1
            except:
                pass
    conn.commit()
    print(f"✅ Fixed {fixed_count} records.")

    # 2. Resolve Pending Scores (Fuzzy Match Active)
    print("🏟️ Resolving pending predictions (Fuzzy Matching enabled)...")
    resolved = scraper.resolve_pending_predictions()
    print(f"✅ Resolved {resolved} matches.")

    # 3. Backfill missing Over 2.5
    print("🔧 Backfilling missing Goals Market data...")
    backfilled = db.backfill_missing_goals_market(ml_predictor=predictor)
    print(f"✅ Backfilled {backfilled} records.")

    print("🏁 Phase 15 Repair Complete.")

if __name__ == "__main__":
    run_fix()

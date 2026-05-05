import logging
import json
import sqlite3
from scraper import IddaaScraper
from database import Database
from ml_predictor import MLPredictor

# Logları ayarla
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()
predictor = MLPredictor(db)
scraper = IddaaScraper(db, predictor)

def verify_and_fix():
    print("\n--- Phase 15 Verification & Fix Start ---")
    
    # 1. Check double encoding
    conn = db.get_connection()
    cursor = conn.execute("SELECT id, goals_market FROM predictions_history WHERE goals_market LIKE '\"{%'")
    bad_rows = cursor.fetchall()
    if bad_rows:
        print(f"⚠️ Found {len(bad_rows)} double-encoded rows. Fixing...")
        for row in bad_rows:
            try:
                # Double encoded: '"{\"over_25\": 65}"' -> '"{\"over_25\": 65}"' (str) -> dict
                clean_json = json.loads(row['goals_market'])
                if isinstance(clean_json, str):
                    clean_json = json.loads(clean_json)
                conn.execute("UPDATE predictions_history SET goals_market = ? WHERE id = ?", (json.dumps(clean_json), row['id']))
            except Exception as e:
                print(f"Error fix {row['id']}: {e}")
        conn.commit()
        print("✅ Double-encoding fixed.")
    else:
        print("✅ No double-encoded rows found.")

    # 2. Trigger Resolution for Pending
    print("\nAttempting to resolve pending predictions...")
    resolved = scraper.resolve_pending_predictions()
    print(f"✅ Resolved {resolved} matches.")

    # 3. Trigger Backfill for Missing Goals Market
    print("\nAttempting to backfill missing Over 2.5 data...")
    backfilled = db.backfill_missing_goals_market(ml_predictor=predictor)
    print(f"✅ Backfilled {backfilled} records.")

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    verify_and_fix()

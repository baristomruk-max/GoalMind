import sqlite3
import json

def debug_db():
    conn = sqlite3.connect('football_data.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("--- PREDICTIONS HISTORY ---")
    cursor.execute("SELECT COUNT(*) FROM predictions_history")
    count = cursor.fetchone()[0]
    print(f"Total predictions: {count}")
    
    if count > 0:
        cursor.execute("SELECT * FROM predictions_history ORDER BY match_date DESC LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            pass
            
    print("\n--- TEAMS IN DB (First 20) ---")
    cursor.execute("SELECT DISTINCT home_team FROM matches LIMIT 20")
    print([r[0] for r in cursor.fetchall()])
    
    print("\n--- TEST SCRAPER FETCH ---")
    from scraper import IddaaScraper
    from ml_predictor import MLPredictor
    from database import Database
    db = Database()
    # Mock predictor to avoid slow loading
    class MockPredictor:
        def predict_match_ml(self, *args, **kwargs):
            return {"probabilities": {"home": 0.5, "draw": 0.3, "away": 0.2}, "prediction": "1", "confidence": 50.0, "tier": "SILVER", "tier_confidence": 0.5}
        def load_model(self): pass
    scraper = IddaaScraper(db, MockPredictor())
    raw = scraper.fetch_upcoming_matches()
    print(f"Raw API events matched: {len(raw)}")
    
    mapped_count = 0
    db_teams = db.get_teams()
    from difflib import get_close_matches
    for match in raw:
        h = get_close_matches(match['home'], db_teams, n=1, cutoff=0.4)
        a = get_close_matches(match['away'], db_teams, n=1, cutoff=0.4)
        if h and a:
            mapped_count += 1
            print(f"MATCHED: {match['home']} -> {h[0]} | {match['away']} -> {a[0]}")
    print(f"Total mapped: {mapped_count}")

if __name__ == '__main__':
    debug_db()

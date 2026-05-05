import logging
from database import Database
import json
import sqlite3

logging.basicConfig(level=logging.INFO)
db = Database()

mock_predictions = [{
    'id': 'test_debug_1',
    'match_date': '2026-03-22',
    'home_team': 'Chelsea',
    'away_team': 'Arsenal',
    'predicted_result': '1',
    'confidence': 65.5,
    'goals_market': {'over_25': 60},
    'win_probabilities': {'home': 65.5, 'draw': 20, 'away': 14.5},
    'league_id': 1,
    'model_version': 'v1.2 (Debug)',
    'tier': '🥇 GOLD',
    'tier_confidence': 70.0,
    'advanced_metrics': {'layers': {}}
}]

print("--- DEBUG: save_predictions_batch starting ---")
try:
    print("Step 1: Connecting...")
    conn = db.get_connection()
    print("Step 2: Cursor...")
    cursor = conn.cursor()
    print("Step 3: BEGIN TRANSACTION...")
    cursor.execute("BEGIN TRANSACTION")
    
    p = mock_predictions[0]
    print("Step 4: Executing INSERT...")
    cursor.execute("""
        INSERT INTO predictions_history 
        (id, match_date, home_team, away_team, predicted_result, confidence, status, 
         goals_market, win_probabilities, league_id, model_version, tier, tier_confidence, advanced_metrics_json)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            predicted_result=excluded.predicted_result,
            confidence=excluded.confidence,
            status='pending',
            goals_market=excluded.goals_market,
            win_probabilities=excluded.win_probabilities,
            league_id=excluded.league_id,
            model_version=excluded.model_version,
            tier=excluded.tier,
            tier_confidence=excluded.tier_confidence,
            advanced_metrics_json=excluded.advanced_metrics_json
    """, (
        p['id'], p['match_date'], p['home_team'], p['away_team'], 
        p['predicted_result'], p['confidence'], 
        json.dumps(p.get('goals_market', {})),
        json.dumps(p.get('win_probabilities', {})),
        p.get('league_id'), p.get('model_version', 'v1.2 (Debug)'),
        p.get('tier'), p.get('tier_confidence'),
        json.dumps(p.get('advanced_metrics', {}))
    ))
    
    print("Step 5: Committing...")
    conn.commit()
    print("✅ Success!")
except sqlite3.Error as e:
    print(f"❌ SQL Error: {e}")
except Exception as e:
    print(f"❌ Other Error: {e}")
finally:
    try: conn.close()
    except: pass

from database import Database
import json
import collections

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("--- Tier Distribution in predictions_history ---")
cursor.execute("SELECT tier, COUNT(*) FROM predictions_history GROUP BY tier")
rows = cursor.fetchall()
for row in rows:
    print(f"{row[0]}: {row[1]}")

print("\n--- Checking Data Quality (Shots) ---")
cursor.execute("SELECT COUNT(*) FROM matches WHERE home_shots IS NOT NULL")
shots_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM matches")
total_count = cursor.fetchone()[0]
print(f"Matches with shot data: {shots_count} / {total_count} ({round(shots_count/total_count*100, 1)}%)")

print("\n--- Sample Prediction Result for Debug ---")
from ml_predictor import MLPredictor
predictor = MLPredictor(db)
teams = db.get_teams()
if len(teams) >= 2:
    res = predictor.predict_match_ml(teams[0], teams[1])
    print(json.dumps(res, indent=4))
else:
    print("Not enough teams.")

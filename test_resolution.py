import logging
import os
from database import Database
from scraper import IddaaScraper
from ml_predictor import MLPredictor
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

# Dummy test setup
print('Veritabanı başlatılıyor...')
db = Database()
db.create_tables()

# Insert a dummy pending prediction for yesterday
last_week = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

# Let's add a dummy pending match
conn = db.get_connection()
conn.execute("""
    INSERT OR REPLACE INTO predictions_history 
    (id, match_date, home_team, away_team, predicted_result, confidence, status, league_id, model_version)
    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
""", ("dummy_event_1", last_week, "Arsenal", "Chelsea", "1", 85.0, 1, "v1.1"))
conn.commit()
print("Dummy pending tahmin eklendi.")

print('Scraper başlatılıyor...')
predictor = MLPredictor(db)
scraper = IddaaScraper(db, predictor)

print('Pending match resolution test...')
resolved = scraper.resolve_pending_predictions()
print(f'Çözümlenen maç sayısı: {resolved}')

print('Metrics in DB:')
cursor = db.get_connection().execute("SELECT * FROM accuracy_analysis ORDER BY id DESC LIMIT 5")
for r in cursor.fetchall():
    print(dict(r))

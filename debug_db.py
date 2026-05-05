
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "football_data.db")
print(f"Veritabanı yolu: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT id, home_team, away_team, match_date, status FROM predictions_history WHERE status = 'pending' LIMIT 10")
    rows = cursor.fetchall()
    
    print(f"Bekleyen maç sayısı (örnek): {len(rows)}")
    for row in rows:
        print(dict(row))
        
    conn.close()
except Exception as e:
    print(f"Hata: {e}")

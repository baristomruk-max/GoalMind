import sqlite3
import json
import sys

db_path = r"e:\KODLAMA\PROJE\FootballData\football_data.db"

def check_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM predictions_history")
    rows = cursor.fetchall()
    
    print(f"Total predictions found: {len(rows)}")
    for row in rows:
        print(dict(row))
    
    conn.close()

if __name__ == "__main__":
    check_db()

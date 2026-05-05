import sqlite3
import os

db_path = 'football_data.db'
if os.path.exists(db_path):
    print(f"Flushing WAL for {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        print("Checkpoint completed (TRUNCATE).")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
else:
    print("DB not found.")

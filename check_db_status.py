import sqlite3
import os

db_path = r'e:\KODLAMA\PROJE\FootballData\football_data.db'

def check_db():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM matches")
        count = cursor.fetchone()[0]
        print(f"Total matches in DB: {count}")
        
        cursor.execute("SELECT MAX(match_date) FROM matches")
        max_date = cursor.fetchone()[0]
        print(f"Latest match date in DB: {max_date}")
        
        cursor.execute("SELECT match_date, COUNT(*) FROM matches WHERE match_date > '2026-03-15' GROUP BY match_date ORDER BY match_date DESC")
        recent_counts = cursor.fetchall()
        print("\nRecent match counts by date:")
        for m_date, cnt in recent_counts:
            print(f"{m_date}: {cnt}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db()

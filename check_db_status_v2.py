import sqlite3
import os

db_path = r'e:\KODLAMA\PROJE\FootballData\football_data.db'
log_path = r'e:\KODLAMA\PROJE\FootballData\db_status.log'

def check_db():
    with open(log_path, 'w', encoding='utf-8') as f:
        if not os.path.exists(db_path):
            f.write(f"Database not found at {db_path}\n")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM matches")
            count = cursor.fetchone()[0]
            f.write(f"Total matches in DB: {count}\n")
            
            cursor.execute("SELECT MAX(date) FROM matches")
            max_date = cursor.fetchone()[0]
            f.write(f"Latest match date in DB: {max_date}\n")
            
            cursor.execute("SELECT date, COUNT(*) FROM matches WHERE date > '2026-03-15' GROUP BY date ORDER BY date DESC")
            recent_counts = cursor.fetchall()
            f.write("\nRecent match counts by date:\n")
            for date, cnt in recent_counts:
                f.write(f"{date}: {cnt}\n")
                
        except Exception as e:
            f.write(f"Error: {e}\n")
        finally:
            conn.close()

if __name__ == "__main__":
    check_db()

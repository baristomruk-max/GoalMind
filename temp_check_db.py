import sqlite3
import os

db_path = r'e:\KODLAMA\PROJE\FootballData\football_data.db'
output_path = r'e:\KODLAMA\PROJE\FootballData\db_count.txt'

def check_db():
    if not os.path.exists(db_path):
        with open(output_path, 'w') as f:
            f.write(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM matches")
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT MAX(match_date) FROM matches")
        max_date = cursor.fetchone()[0]
        
        with open(output_path, 'w') as f:
            f.write(f"Total matches: {count}\n")
            f.write(f"Latest match date: {max_date}\n")
            
    except Exception as e:
        with open(output_path, 'w') as f:
            f.write(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db()

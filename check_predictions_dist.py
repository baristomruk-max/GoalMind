import sqlite3
import os

db_path = r'e:\KODLAMA\PROJE\FootballData\football_data.db'

def check_dist():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        print("Checking predicted_result distribution in predictions_history:")
        cursor.execute("SELECT predicted_result, COUNT(*) as count FROM predictions_history GROUP BY predicted_result")
        rows = cursor.fetchall()
        for row in rows:
            print(f"Result: {row['predicted_result']}, Count: {row['count']}")
            
        print("\nLast 10 predictions:")
        cursor.execute("SELECT match_date, home_team, away_team, predicted_result, confidence FROM predictions_history ORDER BY created_at DESC LIMIT 10")
        for row in cursor.fetchall():
            print(f"{row['match_date']} | {row['home_team']} vs {row['away_team']} | Pred: {row['predicted_result']} | Conf: {row['confidence']}%")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_dist()

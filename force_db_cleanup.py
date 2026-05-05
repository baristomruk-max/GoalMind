import sqlite3
import os

db_path = "football_data.db"

def force_cleanup():
    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        # DB'yi en guncel haline getir
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        
        # 128'li kaydi sil
        conn.execute("DELETE FROM experiments WHERE id = 128")
        
        # Championlari sifirla
        conn.execute("UPDATE experiments SET is_champion = 0")
        
        # En iyisini bul (Profit ve Accuracy bazli)
        res = conn.execute("""
            SELECT id FROM experiments 
            WHERE backtest_profit IS NOT NULL 
            ORDER BY backtest_profit DESC, backtest_accuracy DESC 
            LIMIT 1
        """).fetchone()
        
        if res:
            new_id = res[0]
            print(f"Setting ID {new_id} as the new Champion.")
            conn.execute("UPDATE experiments SET is_champion = 1 WHERE id = ?", (new_id,))
        else:
            print("No valid experiments found for promotion.")

        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        print("Changes committed and checkpoints completed.")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()
        print("Connection closed.")

if __name__ == "__main__":
    force_cleanup()

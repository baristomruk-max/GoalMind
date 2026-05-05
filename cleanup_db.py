from database import Database
from auto_researcher import AutoResearcher

def cleanup():
    db = Database()
    conn = db.get_connection()
    
    # 1. 128'li kaydı bul ve sil
    print("Checking for ID 128...")
    res = conn.execute("SELECT id FROM experiments WHERE id = 128").fetchone()
    if res:
        print("Deleting ID 128...")
        conn.execute("DELETE FROM experiments WHERE id = 128")
        conn.commit()
        print("Deleted.")
    else:
        print("ID 128 not found.")
        
    # 2. Champion'ı sıfırla ve en iyisini ata
    print("Resetting champions...")
    conn.execute("UPDATE experiments SET is_champion = 0")
    conn.commit()
    
    ar = AutoResearcher(db)
    print("Promoting actual historical best...")
    ar.promote_champion()
    
    # 3. Son durumu kontrol et
    champ = db.get_champion_experiment()
    print(f"Current Champion: {champ}")

if __name__ == "__main__":
    cleanup()

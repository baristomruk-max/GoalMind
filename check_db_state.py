from database import Database
db = Database()
conn = db.get_connection()
row = conn.execute("SELECT id, is_champion FROM experiments WHERE id = 128").fetchone()
with open("result_check.txt", "w") as f:
    if row:
        f.write(f"ID 128 exists. Champion: {row['is_champion']}")
    else:
        f.write("ID 128 does not exist.")
        
champ = conn.execute("SELECT id, backtest_profit FROM experiments WHERE is_champion = 1").fetchone()
with open("result_check.txt", "a") as f:
    f.write(f"\nCurrent Champion ID: {champ['id'] if champ else 'None'}")

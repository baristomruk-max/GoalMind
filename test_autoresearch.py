import logging
import sqlite3
from database import Database
from auto_researcher import AutoResearcher

logging.basicConfig(level=logging.INFO)

print("Veritabanı bağlantısı yapılıyor...")
db = Database()

print("AutoResearcher başlatılıyor...")
ar = AutoResearcher(db)

# Optuna varsa çalışacak, 3 deney ile test et
print("Araştırma döngüsü başlatılıyor (Trial Kısıtı: 3)")
ar.run_research_loop(n_experiments=3, time_budget_min=10, continuous=False)

print("İşlem tamamlandı. Veritabanındaki 'experiments' tablosuna kayıtlar atıldı mı kontrol et:")

try:
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT id, cv_score, backtest_accuracy, backtest_profit, duration_sec, error_msg FROM experiments ORDER BY id DESC LIMIT 5")
    rows = c.fetchall()
    print("\n--- Son 5 Deney Kaydı ---")
    for r in rows:
        print(f"ID: {r['id']} | Profit: {r['backtest_profit']} | Acc: {r['backtest_accuracy']} | CV(Test_Acc): {r['cv_score']} | Süre: {r['duration_sec']}s | Hata: {r['error_msg']}")
except Exception as e:
    print(f"Veritabanı okuma hatası: {e}")

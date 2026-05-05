import logging
from database import Database
from auto_researcher import AutoResearcher
import json

logging.basicConfig(level=logging.INFO)
db = Database()
ar = AutoResearcher(db)

def test_promotion():
    print("--- Test: Historical Best Promotion ---")
    
    # 1. Temizlik (Opsiyonel ama güvenli)
    db.get_connection().execute("UPDATE experiments SET is_champion = 0")
    
    # 2. Sahte bir "Best" deney ekle
    # Normalde bu manuel yapılmaz ama testi doğrulamak için:
    db.get_connection().execute("""
        INSERT INTO experiments (config_json, cv_score, train_samples, backtest_accuracy, backtest_profit, is_champion)
        VALUES ('{"test": "best"}', 0.9, 1000, 0.85, 50.5, 0)
    """)
    db.get_connection().commit()
    
    # 3. promote_champion() çağır (argümansız - otomatik en iyiyi seçmeli)
    print("Promoting historical best...")
    ar.promote_champion()
    
    # 4. Kontrol et
    champ = db.get_champion_experiment()
    if champ and champ.get("backtest_profit") == 50.5:
        print("✅ BAŞARILI: Tarihsel en iyi model (Profit 50.5) champion yapıldı.")
    else:
        print(f"❌ HATA: Champion beklenenden farklı: {champ}")

if __name__ == "__main__":
    test_promotion()

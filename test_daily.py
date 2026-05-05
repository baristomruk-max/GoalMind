import logging
import json
from database import Database
from scraper import IddaaScraper
from ml_predictor import MLPredictor

logging.basicConfig(level=logging.INFO)

print('Veritabanı başlatılıyor...')
db = Database()
print('ML Predictor başlatılıyor...')
predictor = MLPredictor(db)
print('Scraper başlatılıyor...')
scraper = IddaaScraper(db, predictor)

print('\nGünün Maçları Çekiliyor (get_daily_predictions)...\n')
result = scraper.get_daily_predictions()

if isinstance(result, dict) and "error" in result:
    print("HATA:", result["error"])
else:
    print(f"Toplam Çekilen: {result.get('total_scraped')}")
    print(f"Toplu Eşleşen (Tahmin Edilen): {result.get('total_mapped')}")
    print(f"Banko Sayısı: {result.get('bankolar_count')}")
    
    print("\n--- GÜNÜN BANKOLARI ---")
    for b in result.get("Günün Bankoları", []):
        print(f"[{b['status']}] {b['home']} vs {b['away']} | Tahmin: {b['prediction']} | Oran: {b['win_probability']}")
        print(f"   Form: {b['features']['home_form_last_10']} vs {b['features']['away_form_last_10']}")
        print(f"   H2H: {b['features']['h2h_history']}")
        print(f"   Sakatlık(Ev): {b['features']['home_injuries']}")
    
    if result.get("total_mapped", 0) > 0 and not result.get("Günün Bankoları"):
        print("Bugün için %70 üzeri güvenilir banko bulunamadı.")
        print("\nÖrnek Normal Tahmin:")
        ex = result["Tüm Tahminler"][0]
        print(f"[{ex['status']}] {ex['home']} vs {ex['away']} | Tahmin: {ex['prediction']} | Oran: {ex['win_probability']}")

print("\nTest Sonlandı.")

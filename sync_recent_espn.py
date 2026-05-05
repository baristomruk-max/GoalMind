from database import Database
from espn_fetcher import EspnResultsFetcher
import logging
from datetime import datetime, timedelta
import os

def log(msg):
    with open("sync_progress.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    print(msg)

def sync_gap():
    # Eski logu sil
    if os.path.exists("sync_progress.log"):
        os.remove("sync_progress.log")
        
    db = Database()
    fetcher = EspnResultsFetcher()
    
    start_date = datetime(2026, 3, 15)
    end_date = datetime(2026, 3, 22)
    
    current_date = start_date
    total_new = 0
    
    log(f"--- ESPN Geriye Dönük Tarama Başlıyor ({start_date.strftime('%Y-%m-%d')} -> {end_date.strftime('%Y-%m-%d')}) ---")
    
    while current_date <= end_date:
        ds = current_date.strftime("%Y%m%d")
        log(f"Fetching matches for {current_date.strftime('%Y-%m-%d')}...")
        
        try:
            matches = fetcher.fetch_results_for_date(ds)
            if matches:
                log(f"  -> ESPN returned {len(matches)} matches.")
                count = db.import_espn_matches(matches)
                total_new += count
                log(f"  -> {count} tanesi veritabanına işlendi.")
            else:
                log("  -> Maç bulunamadı.")
        except Exception as e:
            log(f"  -> Çekim hatası: {e}")
            
        current_date += timedelta(days=1)
        
    log(f"\n--- Tarama Tamamlandı. Toplam {total_new} maç eklendi/güncellendi. ---")
    
    try:
        conn = db.get_connection()
        final_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        log(f"Veritabanındaki güncel toplam maç sayısı: {final_count}")
    except Exception as e:
        log(f"  -> Veritabanı sayım hatası: {e}")

if __name__ == "__main__":
    sync_gap()

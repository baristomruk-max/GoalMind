from database import Database
from api_data_org import FootballDataOrgAPI
from config import SOURCES
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fill_gaps():
    db = Database()
    api_key = SOURCES.get("football-data-org", {}).get("api_key")
    api = FootballDataOrgAPI(api_key=api_key)
    
    # Son 30 günü tara
    print(f"--- 30 Günlük Veri Taraması Başlıyor ({datetime.now().strftime('%Y-%m-%d')}) ---")
    
    # football-data.org'da tek bir istekte tüm maçları çekebiliriz (belirli aralıkta)
    # Ancak ücretsiz planda bazı kısıtlamalar olabilir.
    # Biz son 30 günü 10'ar günlük parçalar halinde çekerek riski azaltalım.
    
    total_imported = 0
    for i in range(3):
        days_ago_to = i * 10
        days_ago_from = (i + 1) * 10
        
        date_to = (datetime.now() - timedelta(days=days_ago_to)).strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=days_ago_from)).strftime("%Y-%m-%d")
        
        print(f"Fetching: {date_from} -> {date_to}")
        
        url = f"{api.base_url}/matches?dateFrom={date_from}&dateTo={date_to}&status=FINISHED"
        try:
            import urllib.request
            import json
            req = urllib.request.Request(url, headers=api.headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode('utf-8'))
                matches = api._parse_matches(data.get("matches", []))
                if matches:
                    count = db.import_api_matches(matches)
                    total_imported += count
                    print(f"  -> {count} maç işlendi.")
                else:
                    print("  -> Maç bulunamadı.")
        except Exception as e:
            print(f"  -> Hata: {e}")
            
    print(f"\n--- Tarama Tamamlandı. Toplam {total_imported} yeni/güncel maç eklendi. ---")

if __name__ == "__main__":
    fill_gaps()

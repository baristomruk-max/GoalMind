import logging
import os
import pandas as pd
from database import Database
from ml_predictor import MLPredictor
from scraper import IddaaScraper

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

def main():
    logger.info("🚀 Manuel Sonuç Çözümleme Başlatılıyor...")
    
    db = Database()
    ml_predictor = MLPredictor(db)
    weekly_scraper = IddaaScraper(db, ml_predictor)
    
    resolved = weekly_scraper.resolve_pending_predictions()
    
    print(f"\n✅ İşlem tamamlandı. Çözümlenen maç sayısı: {resolved}")
    print("Dashboard'u yenileyerek sonuçları görebilirsiniz.")

if __name__ == "__main__":
    main()

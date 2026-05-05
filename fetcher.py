"""
Football Data App - Veri Çekme Motoru
======================================
football-data.co.uk'dan CSV dosyalarını indirir.
Standart ligler ve ekstra ligler için farklı URL formatları desteklenir.
"""

import os
import time
import logging
import urllib.request
import urllib.error
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import (
    BASE_URL, EXTRA_BASE_URL, LEAGUES, EXTRA_LEAGUES, SEASONS,
    STANDARD_DATA_DIR, EXTRA_DATA_DIR, FETCH_CONFIG, SOURCES
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class FootballDataFetcher:
    """football-data.co.uk'dan veri indirme motoru."""

    def __init__(self):
        self.config = FETCH_CONFIG
        self._ensure_dirs()

        # İndirme durumu takibi
        self.status = {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "in_progress": False,
            "errors": [],
            "current_file": "",
        }

    def _ensure_dirs(self):
        """Gerekli klasörleri oluşturur."""
        os.makedirs(STANDARD_DATA_DIR, exist_ok=True)
        os.makedirs(EXTRA_DATA_DIR, exist_ok=True)

    def _download_file(self, url, filepath):
        """
        Tek bir dosyayı standart kütüphane urllib.request ile indirir.
        Diğer yöntemler (requests, curl) engellendiğinde son çare fallback.
        Returns: (success: bool, filepath: str, error: str|None)
        """
        max_retries = self.config["max_retries"]
        retry_delay = self.config["retry_delay"]
        timeout = self.config["timeout"]

        # Sahte bağlam oluştur (SSL hatalarını görmezden gel)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            url, 
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive"
            }
        )

        for attempt in range(1, max_retries + 1):
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
                    # İçerik kontrolü
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" in content_type and "csv" not in content_type:
                        return (False, filepath, f"HTML yanıt alındı (CSV değil): {url}")

                    with open(filepath, "wb") as f:
                        f.write(response.read())

                # Dosya boyutu kontrolü
                if not os.path.exists(filepath):
                    raise Exception("Dosya oluşturulamadı.")

                file_size = os.path.getsize(filepath)
                if file_size < 100:  
                    os.remove(filepath)
                    return (False, filepath, f"Dosya çok küçük veya HTML sayfası ({file_size} byte): {url}")

                logger.info(f"✅ İndirildi: {os.path.basename(filepath)} ({file_size:,} bytes)")
                return (True, filepath, None)

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return (False, filepath, f"404 Not Found: {url}")
                err_msg = str(e)
            except Exception as e:
                err_msg = str(e)

            if attempt < max_retries:
                wait = retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                logger.warning(f"⚠️ Deneme {attempt}/{max_retries} başarısız: {url} - {err_msg}. {wait}s bekleniyor...")
                time.sleep(wait)
            else:
                error_msg = f"❌ Tüm denemeler başarısız: {url} - {err_msg}"
                logger.error(error_msg)
                return (False, filepath, error_msg)

        return (False, filepath, "Bilinmeyen hata")

    def _build_standard_url(self, league_code, season):
        """Standart lig URL'si oluşturur."""
        return f"{BASE_URL}/{season}/{league_code}.csv"

    def _build_extra_url(self, league_code):
        """Ekstra lig URL'si oluşturur."""
        return f"{EXTRA_BASE_URL}/{league_code}.csv"
        
    def _build_alternative_url(self, league_code, season):
        """Alternatif kaynaktan URL oluşturur."""
        alt_base = SOURCES.get("alternative", {}).get("base_url")
        if alt_base:
            return f"{alt_base}/{league_code}/{season}.csv"
        return None

    def _build_standard_filepath(self, league_name, season):
        """Standart lig dosya yolunu oluşturur."""
        safe_name = league_name.replace(" ", "_").replace("-", "_")
        return os.path.join(STANDARD_DATA_DIR, f"{safe_name}_{season}.csv")

    def _build_extra_filepath(self, league_name):
        """Ekstra lig dosya yolunu oluşturur."""
        safe_name = league_name.replace(" ", "_").replace("-", "_")
        return os.path.join(EXTRA_DATA_DIR, f"{safe_name}.csv")

    def fetch_single(self, league_code, season):
        """Tek bir standart lig-sezon çifti indirir."""
        url = self._build_standard_url(league_code, season)
        filepath = os.path.join(STANDARD_DATA_DIR, f"{league_code}_{season}.csv")
        return self._download_file(url, filepath)

    def fetch_all_standard(self, leagues=None, seasons=None):
        """
        Tüm standart liglerin tüm sezonlarını indirir.
        Args:
            leagues: İndirilecek ligler dict (None = tümü)
            seasons: İndirilecek sezonlar listesi (None = tümü)
        Returns: (başarılı_sayı, başarısız_sayı, hatalar_listesi)
        """
        leagues = leagues or LEAGUES
        seasons = seasons or SEASONS

        tasks = []
        for league_name, league_code in leagues.items():
            for season in seasons:
                url = self._build_standard_url(league_code, season)
                filepath = self._build_standard_filepath(league_name, season)
                tasks.append((url, filepath, league_name, season))

        return self._execute_downloads(tasks, "standard")

    def fetch_all_extra(self, leagues=None):
        """
        Tüm ekstra ligleri indirir.
        Args:
            leagues: İndirilecek ligler dict (None = tümü)
        Returns: (başarılı_sayı, başarısız_sayı, hatalar_listesi)
        """
        leagues = leagues or EXTRA_LEAGUES

        tasks = []
        for league_name, league_code in leagues.items():
            url = self._build_extra_url(league_code)
            filepath = self._build_extra_filepath(league_name)
            tasks.append((url, filepath, league_name, None))

        return self._execute_downloads(tasks, "extra")

    def fetch_all(self, only_latest_season=False):
        """Tüm liglerin tüm verilerini indirir."""
        self.status["in_progress"] = True
        self.status["errors"] = []

        target_seasons = [SEASONS[-1]] if only_latest_season else SEASONS

        logger.info("🚀 Tüm veriler indiriliyor..." if not only_latest_season else "⚡ Güncelleme: Sadece son sezon (2526) indiriliyor...")
        logger.info(f"   Standart ligler: {len(LEAGUES)} lig × {len(target_seasons)} sezon")
        logger.info(f"   Ekstra ligler: {len(EXTRA_LEAGUES)} lig")

        # Standart ligler
        s_ok, s_fail, s_errors = self.fetch_all_standard(seasons=target_seasons)
        logger.info(f"📊 Standart ligler: {s_ok} başarılı, {s_fail} başarısız")

        # Ekstra ligler
        e_ok, e_fail, e_errors = self.fetch_all_extra()
        logger.info(f"📊 Ekstra ligler: {e_ok} başarılı, {e_fail} başarısız")

        self.status["in_progress"] = False

        total_ok = s_ok + e_ok
        total_fail = s_fail + e_fail
        all_errors = s_errors + e_errors

        logger.info(f"\n{'='*50}")
        logger.info(f"🏁 TOPLAM: {total_ok} başarılı, {total_fail} başarısız")
        logger.info(f"{'='*50}")

        return total_ok, total_fail, all_errors

    def _execute_downloads(self, tasks, task_type):
        """Sıralı (Single Thread) İndirme Yürütücü (Sunucu banından kaçınmak için)."""
        total = len(tasks)
        self.status["total"] = total
        self.status["completed"] = 0
        self.status["failed"] = 0

        success_count = 0
        fail_count = 0
        errors = []

        logger.info(f"📥 {task_type.upper()} indirme başlatılıyor: {total} dosya (Sıralı indirme)")

        # Paralel indirme yerine sıralı (for loop) indirme yapıyoruz
        # Çünkü football-data.co.uk paralel ve ardışık çoklu isteklere karşı 
        # acımasızca IP/Connection ban (Timeout/Reset) uyguluyor.
        for url, filepath, league_name, season in tasks:
            # Zaten indirilmişse atla
            if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
                success_count += 1
                self.status["completed"] += 1
                continue

            try:
                # İstekler arasına bilinçli gecikme (Rate limiting)
                # Sunucunun bizi bot olarak algılayıp bağlantıyı kesmemesi için kritik!
                time.sleep(2.5) 

                success, _, error = self._download_file(url, filepath)
                
                # Standart kaynak başarısız olursa alternatif kaynağı dene
                if not success and task_type == "standard":
                    alt_url = self._build_alternative_url(url.split("/")[-1].replace(".csv", ""), season)
                    if alt_url:
                        logger.info(f"🔄 Alternatif kaynak deneniyor: {alt_url}")
                        success, _, error = self._download_file(alt_url, filepath)

                if success:
                    success_count += 1
                    self.status["completed"] += 1
                else:
                    fail_count += 1
                    self.status["failed"] += 1
                    if error:
                        err_msg = f"{league_name} ({season}): {error}"
                        errors.append(err_msg)
                        self.status["errors"].append(err_msg)
            except Exception as e:
                fail_count += 1
                self.status["failed"] += 1
                err = f"❌ {league_name} ({season}): {e}"
                errors.append(err)
                self.status["errors"].append(err)

        return success_count, fail_count, errors

    def get_status(self):
        """Mevcut indirme durumunu döndürür."""
        return self.status.copy()

    def get_downloaded_files(self):
        """İndirilmiş dosyaların listesini döndürür."""
        files = {"standard": [], "extra": []}

        if os.path.exists(STANDARD_DATA_DIR):
            files["standard"] = [
                f for f in os.listdir(STANDARD_DATA_DIR) if f.endswith(".csv")
            ]

        if os.path.exists(EXTRA_DATA_DIR):
            files["extra"] = [
                f for f in os.listdir(EXTRA_DATA_DIR) if f.endswith(".csv")
            ]

        return files


if __name__ == "__main__":
    fetcher = FootballDataFetcher()

    # Tek bir lig testi
    print("🔄 Test: England Premier League 2425...")
    success, filepath, error = fetcher.fetch_single("E0", "2425")
    if success:
        print(f"✅ Başarılı: {filepath}")
    else:
        print(f"❌ Hata: {error}")

"""
Auto Updater - Eksik Takım Verisi Tamamlayıcı
================================================
1. Veritabanında aranılan ama bulunamayan takımları tespit eder.
2. football-data.co.uk ve football-data.org API'larından bu takımlara ait verileri çeker.
3. CSV dosyalarını günceller ve veritabanına aktarır.
4. Her gün otomatik çalışır (otonom döngüye entegre).
"""

import os
import logging
import sqlite3
import csv
import time
import json
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta
from database import Database
from config import (
    STANDARD_DATA_DIR, EXTRA_DATA_DIR, SOURCES, DB_PATH,
    LEAGUES, EXTRA_LEAGUES, SEASONS, BASE_URL, EXTRA_BASE_URL
)

logger = logging.getLogger(__name__)


# ─── Kaynak Konfigürasyonları ───────────────────────────────────────────────

FOOTBALL_DATA_ORG_API_KEY = SOURCES.get("football-data-org", {}).get("api_key", "")
FOOTBALL_DATA_ORG_BASE    = SOURCES.get("football-data-org", {}).get("base_url", "https://api.football-data.org/v4")

# football-data.org => yerel lig kodu eşlemesi (ek ligler)
FDORG_COMPETITION_MAP = {
    "PL":  ("England - Premier League", "E0"),
    "PD":  ("Spain - La Liga",          "SP1"),
    "BL1": ("Germany - Bundesliga",      "D1"),
    "SA":  ("Italy - Serie A",           "I1"),
    "FL1": ("France - Ligue 1",          "F1"),
    "DED": ("Netherlands - Eredivisie",  "N1"),
    "PPL": ("Portugal - Liga I",         "P1"),
    "ELC": ("England - Championship",    "E1"),
    "BSA": ("Brazil - Serie A",          "BRA"),
    "CL":  ("UEFA - Champions League",   "UCL"),
}

# SSL sorunlarında bağlantı kurmak için bağlam
def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_get(url, headers=None, timeout=20):
    """Basit HTTP GET yardımcısı. Dict döndürür."""
    req = urllib.request.Request(url, headers=headers or {
        "User-Agent": "Mozilla/5.0 FootballDataBot/1.0",
        "Accept":     "application/json"
    })
    with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ─── 1. Eksik Takım Tespiti ──────────────────────────────────────────────────

def get_missing_teams(db: Database) -> set:
    """
    Son 30 gün içinde tahmin sorgusunda bulunamayan takımları tespit eder.
    Bu takımların geçmiş maç verisi ya hiç yok ya da çok az.
    """
    conn = db.get_connection()
    cur  = conn.cursor()
    missing = set()

    try:
        # Tahmin tablosundaki team'leri al
        cur.execute("""
            SELECT DISTINCT home_team FROM predictions
            WHERE created_at >= datetime('now', '-30 days')
            UNION
            SELECT DISTINCT away_team FROM predictions
            WHERE created_at >= datetime('now', '-30 days')
        """)
        prediction_teams = {row[0] for row in cur.fetchall()}

        # Maç tablosundaki team'leri al
        cur.execute("SELECT DISTINCT home_team FROM matches UNION SELECT DISTINCT away_team FROM matches")
        known_teams = {row[0] for row in cur.fetchall()}

        missing = prediction_teams - known_teams
        if missing:
            logger.info(f"🔍 {len(missing)} eksik takım tespit edildi: {missing}")
        else:
            logger.info("✅ Tüm tahmin takımları veritabanında mevcut.")
    finally:
        cur.close()

    return missing


# ─── 2. football-data.org API'sından Veri Çekme ─────────────────────────────

def fetch_team_matches_from_api(team_name: str) -> list[dict]:
    """
    football-data.org API'sını kullanarak takım adıyla maç verilerini çeker.
    Returns: list of match dicts veya boş liste.
    """
    if not FOOTBALL_DATA_ORG_API_KEY:
        logger.warning("⚠️ football-data.org API anahtarı eksik.")
        return []

    headers = {
        "X-Auth-Token": FOOTBALL_DATA_ORG_API_KEY,
        "Accept":       "application/json",
    }

    try:
        # Takımı isimle ara
        search_url = f"{FOOTBALL_DATA_ORG_BASE}/teams?search={urllib.parse.quote(team_name)}"
        data = _http_get(search_url, headers=headers)
        teams = data.get("teams", [])

        if not teams:
            logger.warning(f"  ❌ API'da takım bulunamadı: {team_name}")
            return []

        team_id = teams[0]["id"]
        team_real_name = teams[0]["name"]
        logger.info(f"  📡 API'dan çekiliyor: {team_real_name} (ID: {team_id})")

        # Son 2 sezon maçlarını çek
        today = datetime.today()
        date_from = (today - timedelta(days=730)).strftime("%Y-%m-%d")
        matches_url = f"{FOOTBALL_DATA_ORG_BASE}/teams/{team_id}/matches?dateFrom={date_from}&status=FINISHED"
        match_data = _http_get(matches_url, headers=headers)
        raw_matches = match_data.get("matches", [])

        # Standart formata çevir
        results = []
        for m in raw_matches:
            try:
                home = m["homeTeam"]["name"]
                away = m["awayTeam"]["name"]
                score = m["score"]["fullTime"]
                result_code = "H" if score["home"] > score["away"] else ("A" if score["home"] < score["away"] else "D")
                date_str = m["utcDate"][:10]
                div = FDORG_COMPETITION_MAP.get(m.get("competition", {}).get("code", ""), ("Unknown", "XX"))[1]

                results.append({
                    "Div":      div,
                    "Date":     date_str,
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "FTHG":     str(score["home"]),
                    "FTAG":     str(score["away"]),
                    "FTR":      result_code,
                    "HTHG":     str(m["score"].get("halfTime", {}).get("home", "")),
                    "HTAG":     str(m["score"].get("halfTime", {}).get("away", "")),
                    "HTR":      "",
                    "B365H":    "", "B365D":    "", "B365A":    "",
                })
            except Exception:
                continue

        logger.info(f"  ✅ {len(results)} maç bulundu: {team_real_name}")
        return results

    except Exception as e:
        logger.error(f"  ❌ API hatası ({team_name}): {e}")
        return []


import urllib.parse  # yukarıdaki çağrı için

# ─── 3. CSV Güncelleme ───────────────────────────────────────────────────────

def _save_matches_to_csv(matches: list[dict], league_key: str):
    """
    Çekilen maçları uygun CSV dosyasına ekler (tekrar eden satırları atlar).
    """
    if not matches:
        return 0

    current_season = SEASONS[-1]  # e.g. "2526"
    filename = f"{league_key}_{current_season}_extra.csv"
    filepath = os.path.join(STANDARD_DATA_DIR, filename)

    fieldnames = [
        "Div", "Date", "HomeTeam", "AwayTeam",
        "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "HTR",
        "B365H", "B365D", "B365A"
    ]

    # Mevcut satırları oku (duplicate kontrol)
    existing_keys = set()
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get("Date",""), row.get("HomeTeam",""), row.get("AwayTeam",""))
                existing_keys.add(key)

    # Yeni satırları yaz
    new_rows = 0
    with open(filepath, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if os.path.getsize(filepath) == 0 or not os.path.exists(filepath):
            writer.writeheader()

        for m in matches:
            key = (m.get("Date",""), m.get("HomeTeam",""), m.get("AwayTeam",""))
            if key not in existing_keys:
                writer.writerow(m)
                existing_keys.add(key)
                new_rows += 1

    if new_rows:
        logger.info(f"  💾 {new_rows} yeni satır kaydedildi: {filepath}")
    return new_rows


# ─── 4. Mevcut CSV'lerin Son Sezon Güncellemesi ──────────────────────────────

def refresh_latest_season_csvs():
    """
    Tüm standart liglerin 2526 (veya cari) sezon CSV'lerini football-data.co.uk'tan
    yeniden indirir. Günde bir kez çağrılmalıdır.
    """
    from fetcher import FootballDataFetcher
    fetcher = FootballDataFetcher()
    current_season = SEASONS[-1]

    updated = 0
    for league_name, league_code in LEAGUES.items():
        safe_name = league_name.replace(" ", "_").replace("-", "_")
        filepath  = os.path.join(STANDARD_DATA_DIR, f"{safe_name}_{current_season}.csv")

        # 12 saatten eskiyse yenile
        if os.path.exists(filepath):
            age_hours = (time.time() - os.path.getmtime(filepath)) / 3600
            if age_hours < 12:
                continue

        url = f"{BASE_URL}/{current_season}/{league_code}.csv"
        success, _, error = fetcher._download_file(url, filepath)
        if success:
            updated += 1
            logger.info(f"  🔄 Güncellendi: {league_name} ({current_season})")
        time.sleep(2)  # Rate limiting

    for league_name, league_code in EXTRA_LEAGUES.items():
        safe_name = league_name.replace(" ", "_").replace("-", "_")
        filepath  = os.path.join(EXTRA_DATA_DIR, f"{safe_name}.csv")

        if os.path.exists(filepath):
            age_hours = (time.time() - os.path.getmtime(filepath)) / 3600
            if age_hours < 12:
                continue

        url = f"{EXTRA_BASE_URL}/{league_code}.csv"
        success, _, error = fetcher._download_file(url, filepath)
        if success:
            updated += 1
            logger.info(f"  🔄 Güncellendi: {league_name} (extra)")
        time.sleep(2)

    logger.info(f"✅ CSV güncelleme tamamlandı: {updated} dosya yenilendi.")
    return updated


# ─── 5. Ana Otomasyon Fonksiyonu ─────────────────────────────────────────────

def run_auto_update(db: Database, import_to_db: bool = True):
    """
    Günlük otonom güncelleme rutini:
    1. Eksik takımları tespit et
    2. Alternatif kaynaklardan veri çek → CSV'ye kaydet
    3. Cari sezon CSV'lerini yenile
    4. Veritabanını güncelle
    """
    logger.info("🚀 [AutoUpdater] Günlük veri güncelleme başlatıldı...")

    # 1. Eksik takımları bul ve API'dan çek
    missing = get_missing_teams(db)
    total_new_rows = 0
    for team in missing:
        logger.info(f"  🔎 Takım aranıyor: {team}")
        matches = fetch_team_matches_from_api(team)
        if matches:
            # İlk maçın Div bilgisine göre kaydet
            div_key = matches[0].get("Div", "EXTRA") if matches else "EXTRA"
            total_new_rows += _save_matches_to_csv(matches, div_key)
        time.sleep(1)  # API rate limiting

    # 2. Cari sezon CSV güncellemesi
    try:
        updated = refresh_latest_season_csvs()
        logger.info(f"  📊 {updated} CSV güncellendi.")
    except Exception as e:
        logger.error(f"  ❌ CSV güncelleme hatası: {e}")

    # 3. Veritabanına aktar
    if import_to_db and (total_new_rows > 0):
        try:
            db.import_all_csvs()
            logger.info("  ✅ Veritabanı güncellendi.")
        except Exception as e:
            logger.error(f"  ❌ DB import hatası: {e}")

    logger.info("✅ [AutoUpdater] Güncelleme tamamlandı.")
    return total_new_rows


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    db = Database()
    run_auto_update(db)

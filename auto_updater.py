"""
Auto Updater - Eksik Takım Verisi Tamamlayıcı (CSV Tabanlı)
==========================================================
SQLite bağımlılığı kaldırılmıştır. Veriler Pandas ile işlenir.
"""

import os
import logging
import csv
import time
import json
import urllib.request
import urllib.error
import ssl
import pandas as pd
from datetime import datetime, timedelta
from database import Database
from config import (
    STANDARD_DATA_DIR, EXTRA_DATA_DIR, SOURCES, 
    LEAGUES, EXTRA_LEAGUES, SEASONS, BASE_URL, EXTRA_BASE_URL
)

logger = logging.getLogger(__name__)

# ─── Kaynak Konfigürasyonları ───────────────────────────────────────────────

FOOTBALL_DATA_ORG_API_KEY = SOURCES.get("football-data-org", {}).get("api_key", "")
FOOTBALL_DATA_ORG_BASE    = SOURCES.get("football-data-org", {}).get("base_url", "https://api.football-data.org/v4")

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

def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def _http_get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {
        "User-Agent": "Mozilla/5.0 FootballDataBot/1.0",
        "Accept":     "application/json"
    })
    with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=timeout) as resp:
        return json.loads(resp.read().decode())

# ─── 1. Eksik Takım Tespiti ──────────────────────────────────────────────────

def get_missing_teams(db: Database) -> set:
    """Son 30 gün içindeki tahminlerdeki ama maç verisi olmayan takımları bulur."""
    try:
        # Tahminleri SQLite'dan oku
        from datetime import datetime, timedelta
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT home_team, away_team FROM predictions WHERE created_at >= ?",
                ((datetime.now() - timedelta(days=30)).isoformat(),)
            ).fetchall()
        prediction_teams = set()
        for r in rows:
            if r['home_team']:
                prediction_teams.add(r['home_team'])
            if r['away_team']:
                prediction_teams.add(r['away_team'])

        # Mevcut maçlardaki takımları al
        known_teams = set(db.get_teams())
        
        missing = {t for t in prediction_teams if t and str(t) != 'nan'} - known_teams
        if missing:
            logger.info(f"🔍 {len(missing)} eksik takım tespit edildi: {missing}")
        return missing
    except Exception as e:
        logger.error(f"Eksik takım tespiti hatası: {e}")
        return set()

# ─── 2. football-data.org API'sından Veri Çekme ─────────────────────────────

def fetch_team_matches_from_api(team_name: str) -> list[dict]:
    if not FOOTBALL_DATA_ORG_API_KEY: return []
    headers = {"X-Auth-Token": FOOTBALL_DATA_ORG_API_KEY, "Accept": "application/json"}

    try:
        search_url = f"{FOOTBALL_DATA_ORG_BASE}/teams?search={urllib.parse.quote(team_name)}"
        data = _http_get(search_url, headers=headers)
        teams = data.get("teams", [])
        if not teams: return []

        team_id = teams[0]["id"]
        matches_url = f"{FOOTBALL_DATA_ORG_BASE}/teams/{team_id}/matches?dateFrom={(datetime.today() - timedelta(days=730)).strftime('%Y-%m-%d')}&status=FINISHED"
        match_data = _http_get(matches_url, headers=headers)
        raw_matches = match_data.get("matches", [])

        results = []
        for m in raw_matches:
            try:
                score = m["score"]["fullTime"]
                results.append({
                    "Div":      FDORG_COMPETITION_MAP.get(m.get("competition", {}).get("code", ""), ("Unknown", "XX"))[1],
                    "Date":     m["utcDate"][:10],
                    "HomeTeam": m["homeTeam"]["name"],
                    "AwayTeam": m["awayTeam"]["name"],
                    "FTHG":     str(score["home"]),
                    "FTAG":     str(score["away"]),
                    "FTR":      "H" if score["home"] > score["away"] else ("A" if score["home"] < score["away"] else "D"),
                    "HTHG":     str(m["score"].get("halfTime", {}).get("home", "")),
                    "HTAG":     str(m["score"].get("halfTime", {}).get("away", "")),
                    "HTR":      "",
                })
            except: continue
        return results
    except Exception as e:
        logger.error(f"API hatası ({team_name}): {e}")
        return []

import urllib.parse

# ─── 3. CSV Güncelleme ───────────────────────────────────────────────────────

def _save_matches_to_csv(matches: list[dict], league_key: str):
    if not matches: return 0
    current_season = SEASONS[-1]
    filename = f"{league_key}_{current_season}_extra.csv"
    filepath = os.path.join(STANDARD_DATA_DIR, filename)

    df_new = pd.DataFrame(matches)
    if os.path.exists(filepath):
        df_old = pd.read_csv(filepath)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Date', 'HomeTeam', 'AwayTeam'], keep='last')
    else:
        df_final = df_new
        
    df_final.to_csv(filepath, index=False, encoding="utf-8")
    return len(df_new)

# ─── 4. Mevcut CSV'lerin Son Sezon Güncellemesi ──────────────────────────────

def refresh_latest_season_csvs():
    from fetcher import FootballDataFetcher
    fetcher = FootballDataFetcher()
    current_season = SEASONS[-1]
    updated = 0
    
    for league_name, league_code in {**LEAGUES, **EXTRA_LEAGUES}.items():
        is_extra = league_name in EXTRA_LEAGUES
        safe_name = league_name.replace(" ", "_").replace("-", "_")
        target_dir = EXTRA_DATA_DIR if is_extra else STANDARD_DATA_DIR
        filepath = os.path.join(target_dir, f"{safe_name}_{current_season}.csv" if not is_extra else f"{safe_name}.csv")
        
        if os.path.exists(filepath) and (time.time() - os.path.getmtime(filepath)) < 43200: # 12 saat
            continue
            
        url = f"{EXTRA_BASE_URL}/{league_code}.csv" if is_extra else f"{BASE_URL}/{current_season}/{league_code}.csv"
        success, _, _ = fetcher._download_file(url, filepath)
        if success: updated += 1
        time.sleep(1)
        
    return updated

# ─── 5. Ana Otomasyon Fonksiyonu ─────────────────────────────────────────────

def run_auto_update(db: Database, import_to_db: bool = True):
    logger.info("🚀 [AutoUpdater] CSV Güncelleme başlatıldı...")
    missing = get_missing_teams(db)
    new_rows = 0
    for team in missing:
        matches = fetch_team_matches_from_api(team)
        if matches:
            new_rows += _save_matches_to_csv(matches, matches[0].get("Div", "EXTRA"))
        time.sleep(1)

    refresh_latest_season_csvs()
    if import_to_db:
        db.reload_data()
    logger.info("✅ Güncelleme tamamlandı.")
    return new_rows

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = Database()
    run_auto_update(db)

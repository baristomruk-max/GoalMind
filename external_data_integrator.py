"""
External Data Integrator (CSV Tabanlı)
=======================================
Understat xG ve ClubElo verilerini CSV dosyalarında saklar.
SQLite bağımlılığı kaldırılmıştır.
"""

import os
import json
import logging
import time
import urllib.request
import urllib.error
import ssl
import csv
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from database import Database
from config import DATA_DIR

logger = logging.getLogger(__name__)

ELO_FILE = os.path.join(DATA_DIR, "team_elo_ratings.csv")
XG_FILE = os.path.join(DATA_DIR, "understat_xg.csv")

def _init_files():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ELO_FILE):
        pd.DataFrame(columns=["team_name", "elo", "updated_at"]).to_csv(ELO_FILE, index=False)
    if not os.path.exists(XG_FILE):
        pd.DataFrame(columns=["match_date", "home_team", "away_team", "home_xg", "away_xg", "league", "season"]).to_csv(XG_FILE, index=False)

_init_files()

def _get(url: str, headers: dict = None, timeout: int = 20, mode="json"):
    req = urllib.request.Request(url, headers=headers or {
        "User-Agent": "Mozilla/5.0 FootballDataBot/2.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            if mode == "json":
                return json.loads(raw)
            return raw
    except Exception as e:
        logger.warning(f"GET hatası: {url} — {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════
#  1. UNDERSTAT — xG Verisi
# ═══════════════════════════════════════════════════════════════════════

UNDERSTAT_LEAGUES = {
    "EPL":        "England - Premier League",
    "La_liga":    "Spain - La Liga",
    "Bundesliga": "Germany - Bundesliga",
    "Serie_A":    "Italy - Serie A",
    "Ligue_1":    "France - Ligue 1",
    "RFPL":       "Russia - Premier League",
}

def fetch_understat_xg(league_code: str = "EPL", season: int = 2024) -> list[dict]:
    url = f"https://understat.com/league/{league_code}/{season}"
    html = _get(url, mode="text")
    if not html: return []

    import re
    pattern = r"var datesData\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html)
    if not match: return []

    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    try:
        matches = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Understat JSON parse hatası: {e}")
        return []

    results = []
    for m in matches:
        if m.get("isResult") != True: continue
        results.append({
            "match_date": m.get("datetime", "")[:10],
            "home_team":  m.get("h", {}).get("title", ""),
            "away_team":  m.get("a", {}).get("title", ""),
            "home_goals": m.get("goals", {}).get("h"),
            "away_goals": m.get("goals", {}).get("a"),
            "home_xg":    m.get("xG", {}).get("h"),
            "away_xg":    m.get("xG", {}).get("a"),
            "league":     UNDERSTAT_LEAGUES.get(league_code, league_code),
            "season":     season,
        })
    return results

def store_understat_xg(db: Database, matches: list[dict]) -> int:
    if not matches: return 0
    df_new = pd.DataFrame(matches)
    if os.path.exists(XG_FILE):
        df_old = pd.read_csv(XG_FILE)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['match_date', 'home_team', 'away_team'], keep='last')
    else:
        df_final = df_new
    df_final.to_csv(XG_FILE, index=False)
    return len(df_new)

# ═══════════════════════════════════════════════════════════════════════
#  2. CLUBELO — Takım ELO Derecelendirmesi
# ═══════════════════════════════════════════════════════════════════════

def fetch_clubelo_rating(team_name: str) -> Optional[float]:
    import urllib.parse
    slug = team_name.replace(" ", "")
    # Turkish chars → ASCII mapping for ClubElo API
    turkish_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    slug = slug.translate(turkish_map)
    url  = f"http://api.clubelo.com/{urllib.parse.quote(slug)}"
    raw  = _get(url, mode="text")
    if not raw: return None
    lines = raw.strip().split("\n")
    if len(lines) < 2: return None
    try:
        last = lines[-1].split(",")
        return float(last[4])
    except (IndexError, ValueError) as e:
        logger.warning(f"ClubElo parse hatası ({team_name}): {e}")
        return None

def fetch_clubelo_batch(team_names: list[str]) -> dict[str, float]:
    results = {}
    for team in team_names:
        elo = fetch_clubelo_rating(team)
        if elo: results[team] = elo
        time.sleep(0.5)
    return results

def store_clubelo_ratings(db: Database, ratings: dict[str, float]) -> int:
    if not ratings: return 0
    now = datetime.now().isoformat()
    rows = [{"team_name": t, "elo": e, "updated_at": now} for t, e in ratings.items()]
    df_new = pd.DataFrame(rows)
    
    if os.path.exists(ELO_FILE):
        df_old = pd.read_csv(ELO_FILE)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['team_name'], keep='last')
    else:
        df_final = df_new
    df_final.to_csv(ELO_FILE, index=False)
    return len(df_new)

def get_elo_for_prediction(db: Database, home_team: str, away_team: str) -> dict:
    if not os.path.exists(ELO_FILE): return {}
    df = pd.read_csv(ELO_FILE)
    
    def _get_elo(team):
        res = df[df['team_name'].str.contains(team[:6], case=False, na=False)]
        if not res.empty:
            return float(res.iloc[-1]['elo'])
        return fetch_clubelo_rating(team)

    h_elo = _get_elo(home_team)
    a_elo = _get_elo(away_team)
    
    if h_elo and a_elo:
        diff = h_elo - a_elo
        expected = 1 / (1 + 10 ** (-diff / 400))
        return {
            "home_elo": round(h_elo, 0), "away_elo": round(a_elo, 0),
            "elo_diff": round(diff, 0), "elo_expected_home_win": round(expected * 100, 1)
        }
    return {}

# ═══════════════════════════════════════════════════════════════════════
#  4. Tahmin Zenginleştirici
# ═══════════════════════════════════════════════════════════════════════

def enrich_prediction_with_external(db: Database, prediction: dict) -> dict:
    try:
        home = prediction.get("teams", {}).get("home", "")
        away = prediction.get("teams", {}).get("away", "")
        
        elo_data = get_elo_for_prediction(db, home, away)
        if elo_data: prediction["elo_data"] = elo_data

        if os.path.exists(XG_FILE):
            df_xg = pd.read_csv(XG_FILE)
            h_xg = df_xg[df_xg['home_team'].str.contains(home[:6], case=False, na=False)]['home_xg'].tail(5).mean()
            a_xg = df_xg[df_xg['away_team'].str.contains(away[:6], case=False, na=False)]['away_xg'].tail(5).mean()
            
            if pd.notna(h_xg): prediction.setdefault("advanced_metrics", {})["home_avg_xg_5"] = round(h_xg, 2)
            if pd.notna(a_xg): prediction.setdefault("advanced_metrics", {})["away_avg_xg_5"] = round(a_xg, 2)

        prediction["external_sources"] = ["clubelo.com", "understat.com"]
    except Exception as e:
        logger.warning(f"Zenginleştirme hatası: {e}")
    return prediction

def run_external_data_sync(db: Database):
    logger.info("🌐 [ExternalData] CSV Tabanlı senkronizasyon başlatıldı...")
    _init_files()
    
    # Understat
    current_year = datetime.now().year
    season_year = current_year - 1 if datetime.now().month < 7 else current_year
    for code, name in UNDERSTAT_LEAGUES.items():
        try:
            matches = fetch_understat_xg(code, season_year)
            store_understat_xg(db, matches)
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Understat {code} senkronizasyon hatası: {e}")

    # ClubElo (Örnek 20 takım)
    teams = db.get_teams()[:20]
    ratings = fetch_clubelo_batch(teams)
    store_clubelo_ratings(db, ratings)
    logger.info("✅ Senkronizasyon tamamlandı.")

if __name__ == "__main__":
    db = Database()
    run_external_data_sync(db)

"""
External Data Integrator
========================
eddwebster/football_analytics reposundan ilham alınarak hazırlanmış
çoklu kaynak veri entegrasyon modülü.

Desteklenen ücretsiz kaynaklar:
1. Understat   – xG (Beklenen Gol) verisi for Big 5 ligler
2. ClubElo     – Takım ELO derecelendirmesi (tahmin gücü hesabı için)
3. StatsBomb   – Açık event verisi (GitHub raw CSV/JSON)

Her kaynak için:
  * fetch_*()  → Ham veriyi çeker
  * store_*()  → Veritabanına/CSV'ye kaydeder
  * enrich_prediction() → Tahmin sonucunu zenginleştirir
"""

import os
import json
import sqlite3
import logging
import time
import urllib.request
import urllib.error
import ssl
import csv
from datetime import datetime, timedelta
from typing import Optional
from database import Database

logger = logging.getLogger(__name__)


# ─── SSL bağlam yardımcısı ──────────────────────────────────────────────────

def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _get(url: str, headers: dict = None, timeout: int = 20, mode="json"):
    """Basit HTTP GET — JSON veya metin döndürür."""
    req = urllib.request.Request(url, headers=headers or {
        "User-Agent": "Mozilla/5.0 FootballDataBot/2.0"
    })
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            if mode == "json":
                return json.loads(raw)
            return raw
    except Exception as e:
        logger.warning(f"GET hatası: {url} — {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════
#  1. UNDERSTAT — xG Verisi
#     https://understat.com/
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
    """
    Understat'tan belirtilen lig-sezon için tüm takımların xG verisini çeker.
    Returns: list of {home, away, scored, missed, xG, xGA, date, ...}
    """
    url = f"https://understat.com/league/{league_code}/{season}"
    html = _get(url, mode="text")
    if not html:
        return []

    import re
    # Understat, verisini JSON içeren bir JS değişkenine gömer
    pattern = r"var datesData\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html)
    if not match:
        logger.warning(f"Understat: datesData bulunamadı ({league_code} {season})")
        return []

    raw = match.group(1)
    # Python unicode escape dönüşümü
    raw = raw.encode("utf-8").decode("unicode_escape")
    try:
        matches = json.loads(raw)
    except Exception as e:
        logger.error(f"Understat JSON parse hatası: {e}")
        return []

    results = []
    for m in matches:
        if m.get("isResult") != True:
            continue
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
    logger.info(f"Understat: {len(results)} maç alındı ({league_code} {season})")
    return results


def store_understat_xg(db: Database, matches: list[dict]) -> int:
    """
    xG verilerini veritabanındaki matches tablosuna günceller.
    Sadece mevcut maçların home_xg / away_xg sütunlarını doldurur.
    """
    if not matches:
        return 0

    conn = db.get_connection()
    cur  = conn.cursor()

    # Önce sütunların mevcut olup olmadığını kontrol et
    cur.execute("PRAGMA table_info(matches)")
    cols = {row["name"] for row in cur.fetchall()}

    if "home_xg" not in cols:
        cur.execute("ALTER TABLE matches ADD COLUMN home_xg REAL DEFAULT NULL")
    if "away_xg" not in cols:
        cur.execute("ALTER TABLE matches ADD COLUMN away_xg REAL DEFAULT NULL")

    updated = 0
    for m in matches:
        try:
            cur.execute("""
                UPDATE matches
                SET home_xg = ?, away_xg = ?
                WHERE date(match_date) = date(?)
                  AND home_team LIKE ?
                  AND away_team LIKE ?
            """, (
                m["home_xg"], m["away_xg"],
                m["match_date"],
                f"%{m['home_team'][:6]}%",
                f"%{m['away_team'][:6]}%"
            ))
            updated += cur.rowcount
        except Exception:
            pass

    conn.commit()
    cur.close()
    logger.info(f"Understat: {updated} maç güncellendi (xG verileri).")
    return updated


# ═══════════════════════════════════════════════════════════════════════
#  2. CLUBELO — Takım ELO Derecelendirmesi
#     http://clubelo.com/API
# ═══════════════════════════════════════════════════════════════════════

def fetch_clubelo_rating(team_name: str) -> Optional[float]:
    """
    clubelo.com API'sından bir takımın güncel ELO puanını çeker.
    Returns: float ELO puanı veya None.
    """
    # ELO API: http://api.clubelo.com/TeamName
    slug = team_name.replace(" ", "")  # "Manchester City" → "ManchesterCity"
    url  = f"http://api.clubelo.com/{slug}"
    raw  = _get(url, mode="text")
    if not raw:
        return None

    # CSV formatı: Rank,Club,Country,Level,Elo,From,To
    lines = raw.strip().split("\n")
    if len(lines) < 2:
        return None
    try:
        last = lines[-1].split(",")
        elo  = float(last[4])
        return elo
    except Exception:
        return None


def fetch_clubelo_batch(team_names: list[str]) -> dict[str, float]:
    """
    Birden fazla takım için ELO derecelendirmesi çeker.
    Returns: {team_name: elo_score}
    """
    results = {}
    for team in team_names:
        elo = fetch_clubelo_rating(team)
        if elo:
            results[team] = elo
            logger.info(f"ClubElo: {team} → {elo:.0f}")
        time.sleep(0.5)  # Rate limiting
    return results


def store_clubelo_ratings(db: Database, ratings: dict[str, float]) -> int:
    """
    ELO puanlarını veritabanına kaydeder (team_elo_ratings tablosu).
    """
    if not ratings:
        return 0

    conn = db.get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_elo_ratings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name  TEXT NOT NULL,
            elo        REAL NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    now = datetime.now().isoformat()
    saved = 0
    for team, elo in ratings.items():
        # Varsa güncelle, yoksa ekle
        cur.execute("SELECT id FROM team_elo_ratings WHERE team_name = ?", (team,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE team_elo_ratings SET elo=?, updated_at=? WHERE team_name=?",
                        (elo, now, team))
        else:
            cur.execute("INSERT INTO team_elo_ratings (team_name, elo, updated_at) VALUES (?,?,?)",
                        (team, elo, now))
        saved += 1

    conn.commit()
    cur.close()
    logger.info(f"ClubElo: {saved} takım ELO puanı veritabanına kaydedildi.")
    return saved


def get_elo_for_prediction(db: Database, home_team: str, away_team: str) -> dict:
    """
    Tahmin sırasında iki takımın ELO puanlarını ve farkını döndürür.
    Yoksa önce API'dan çeker.
    """
    conn = db.get_connection()
    cur  = conn.cursor()

    def _db_elo(team):
        cur.execute("""
            SELECT elo, updated_at FROM team_elo_ratings
            WHERE team_name LIKE ? ORDER BY updated_at DESC LIMIT 1
        """, (f"%{team[:8]}%",))
        row = cur.fetchone()
        if row:
            age = (datetime.now() - datetime.fromisoformat(row["updated_at"])).days
            if age < 7:  # 7 günden eskiyse yenile
                return float(row["elo"])
        return None

    home_elo = _db_elo(home_team) or fetch_clubelo_rating(home_team)
    away_elo = _db_elo(away_team) or fetch_clubelo_rating(away_team)
    cur.close()

    if home_elo and away_elo:
        elo_diff = home_elo - away_elo
        # ELO farkından tahmin: her 400 puan ≈ %91 kazanma şansı
        import math
        expected_home = 1 / (1 + 10 ** (-elo_diff / 400))
        return {
            "home_elo": round(home_elo, 0),
            "away_elo": round(away_elo, 0),
            "elo_diff": round(elo_diff, 0),
            "elo_expected_home_win": round(expected_home * 100, 1),
        }
    return {}


# ═══════════════════════════════════════════════════════════════════════
#  3. STATSBOMB — Açık Event Verisi
#     https://github.com/statsbomb/open-data
# ═══════════════════════════════════════════════════════════════════════

STATSBOMB_RAW  = "https://raw.githubusercontent.com/statsbomb/open-data/master"


def fetch_statsbomb_competitions() -> list[dict]:
    """StatsBomb açık veri yarışmalarını çeker."""
    url  = f"{STATSBOMB_RAW}/data/competitions.json"
    data = _get(url)
    return data or []


def fetch_statsbomb_matches(competition_id: int, season_id: int) -> list[dict]:
    """Belirtilen yarışma-sezon çiftinin maç listesini çeker."""
    url  = f"{STATSBOMB_RAW}/data/matches/{competition_id}/{season_id}.json"
    data = _get(url)
    return data or []


def get_statsbomb_xg_for_match(match_id: int) -> dict:
    """
    Belirli bir maçın olaylarından xG bilgisini çıkarır.
    Returns: {"home_xg": float, "away_xg": float}
    """
    url    = f"{STATSBOMB_RAW}/data/events/{match_id}.json"
    events = _get(url)
    if not events:
        return {}

    home_xg = away_xg = 0.0
    home_team = away_team = None

    for ev in events:
        if ev.get("type", {}).get("name") == "Shot":
            xg = ev.get("shot", {}).get("statsbomb_xg", 0)
            team = ev.get("team", {}).get("name", "")
            if home_team is None and ev.get("location"):
                home_team = team
            if team == home_team:
                home_xg += xg
            else:
                away_xg += xg

    return {
        "home_xg": round(home_xg, 3),
        "away_xg": round(away_xg, 3)
    }


# ═══════════════════════════════════════════════════════════════════════
#  4. Tahmin Zenginleştirici
# ═══════════════════════════════════════════════════════════════════════

def enrich_prediction_with_external(db: Database, prediction: dict) -> dict:
    """
    Mevcut bir tahmin sonucunu ELO ve xG verileriyle zenginleştirir.
    prediction dict'e 'elo_data' ve 'external_sources' anahtarları eklenir.
    """
    try:
        home = prediction.get("teams", {}).get("home", "")
        away = prediction.get("teams", {}).get("away", "")

        # ELO verileri
        elo_data = get_elo_for_prediction(db, home, away)
        if elo_data:
            prediction["elo_data"] = elo_data

        # xG geçmişi (son 5 maçtan ortalama)
        conn = db.get_connection()
        cur  = conn.cursor()
        for col in ["home_xg", "away_xg"]:
            cur.execute("PRAGMA table_info(matches)")
            if col not in {r["name"] for r in cur.fetchall()}:
                cur.close()
                return prediction

        cur.execute("""
            SELECT AVG(home_xg), AVG(away_xg) FROM (
                SELECT home_xg, away_xg FROM matches
                WHERE home_team LIKE ? AND home_xg IS NOT NULL
                ORDER BY match_date DESC LIMIT 5
            )
        """, (f"%{home[:6]}%",))
        row = cur.fetchone()
        if row and row[0]:
            prediction.setdefault("advanced_metrics", {})["home_avg_xg_5"] = round(row[0], 2)

        cur.execute("""
            SELECT AVG(home_xg), AVG(away_xg) FROM (
                SELECT home_xg, away_xg FROM matches
                WHERE away_team LIKE ? AND away_xg IS NOT NULL
                ORDER BY match_date DESC LIMIT 5
            )
        """, (f"%{away[:6]}%",))
        row = cur.fetchone()
        if row and row[1]:
            prediction.setdefault("advanced_metrics", {})["away_avg_xg_5"] = round(row[1], 2)

        cur.close()
        prediction["external_sources"] = ["clubelo.com", "understat.com"]

    except Exception as e:
        logger.warning(f"Tahmin zenginleştirme hatası: {e}")

    return prediction


# ═══════════════════════════════════════════════════════════════════════
#  5. Günlük Veri Çekme Rutini
# ═══════════════════════════════════════════════════════════════════════

def run_external_data_sync(db: Database):
    """
    Günlük olarak çalışacak harici veri senkronizasyonu:
    1. Understat xG verilerini çek ve kaydet (Big-5 ligler, cari sezon)
    2. Aktif takımların ELO puanlarını güncelle
    """
    logger.info("🌐 [ExternalData] Harici veri senkronizasyonu başlatıldı...")

    current_year = datetime.now().year
    if datetime.now().month < 7:
        season_year = current_year - 1
    else:
        season_year = current_year

    # 1. Understat xG
    for code, name in UNDERSTAT_LEAGUES.items():
        try:
            logger.info(f"  📡 Understat çekiliyor: {name} {season_year}")
            matches = fetch_understat_xg(code, season_year)
            store_understat_xg(db, matches)
            time.sleep(3)  # Rate limiting
        except Exception as e:
            logger.error(f"  Understat hatası ({name}): {e}")

    # 2. ClubElo — Aktif takımlar
    try:
        conn = db.get_connection()
        cur  = conn.cursor()
        cur.execute("""
            SELECT DISTINCT home_team FROM matches
            WHERE match_date >= date('now', '-90 days')
            LIMIT 60
        """)
        active_teams = [row[0] for row in cur.fetchall() if row[0]]
        cur.close()

        ratings = fetch_clubelo_batch(active_teams)
        store_clubelo_ratings(db, ratings)
    except Exception as e:
        logger.error(f"  ClubElo güncelleme hatası: {e}")

    logger.info("✅ [ExternalData] Harici veri senkronizasyonu tamamlandı.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    db = Database()
    run_external_data_sync(db)

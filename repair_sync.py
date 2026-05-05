import urllib.request
import json
import os
import sqlite3
import ssl
from datetime import datetime, timedelta

# SSL kapat (Sertifika hatalarını önlemek için)
ssl_ctx = ssl._create_unverified_context()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "football_data.db")

def log(msg):
    with open("sync_repair.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
    print(msg)

def run_repair_sync():
    if os.path.exists("sync_repair.log"): os.remove("sync_repair.log")
    log("Starting Repair Sync (ESPN)...")
    
    # 1. League Mapping
    mapping_file = os.path.join(BASE_DIR, "data", "espn_league_mappings.json")
    with open(mapping_file, "r") as f:
        league_map = json.load(f)
    
    # 2. Team Mapper Mock (Hızlı eşleme için basitleştirilmiş)
    # Gerçek TeamMapper'ı kullanalım
    from team_mapper import TeamMapper
    mapper = TeamMapper()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    days_to_sync = [
        "20260318", "20260319", "20260320", "20260321", "20260322"
    ]
    
    total_added = 0
    for ds in days_to_sync:
        log(f"Fetching {ds}...")
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}&limit=500"
        
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
                events = data.get("events", [])
                log(f"  -> Found {len(events)} events.")
                
                for event in events:
                    status = event.get("status", {}).get("type", {}).get("name")
                    if status != "STATUS_FULL_TIME": continue
                    
                    comp = event.get("competitions", [{}])[0]
                    espn_league = comp.get("notes", [{}])[0].get("headline") if comp.get("notes") else event.get("league", {}).get("name")
                    
                    target_code = None
                    if espn_league:
                        espn_league_lower = espn_league.lower()
                        for k, v in league_map.items():
                            if k.lower() in espn_league_lower or espn_league_lower in k.lower():
                                target_code = v
                                break
                    
                    if not target_code: continue
                    
                    # DB Liga ID
                    cursor.execute("SELECT id FROM leagues WHERE code = ?", (target_code,))
                    l_row = cursor.fetchone()
                    if not l_row: continue
                    league_id = l_row["id"]
                    
                    competitors = comp.get("competitors", [])
                    home_raw, away_raw, h_score, a_score = "", "", 0, 0
                    for c in competitors:
                        if c.get("homeAway") == "home":
                            home_raw, h_score = c.get("team", {}).get("name"), int(c.get("score", 0))
                        else:
                            away_raw, a_score = c.get("team", {}).get("name"), int(c.get("score", 0))
                    
                    home = mapper.normalize(home_raw)
                    away = mapper.normalize(away_raw)
                    m_date = event.get("date")[:10]
                    
                    # FTR
                    ftr = "D"
                    if h_score > a_score: ftr = "H"
                    elif a_score > h_score: ftr = "A"
                    
                    try:
                        cursor.execute("""
                            INSERT INTO matches (league_id, match_date, home_team, away_team, fthg, ftag, ftr)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(league_id, match_date, home_team, away_team) DO UPDATE SET
                                fthg=excluded.fthg, ftag=excluded.ftag, ftr=excluded.ftr
                        """, (league_id, m_date, home, away, h_score, a_score, ftr))
                        if cursor.rowcount > 0: total_added += 1
                    except Exception as e:
                        log(f"    Insert error: {e}")
                
                conn.commit()
                log(f"  -> Committed. Total so far: {total_added}")
        except Exception as e:
            log(f"  -> Fetch error: {e}")
            
    conn.close()
    log(f"DONE. Total Matches added/updated: {total_added}")

if __name__ == "__main__":
    run_repair_sync()

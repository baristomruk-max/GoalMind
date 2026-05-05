import urllib.request
import json
import os
import sqlite3
import ssl
from datetime import datetime

# SSL bypass
ssl_ctx = ssl._create_unverified_context()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "football_data.db")
LOG_PATH = os.path.join(BASE_DIR, "sync_standalone.log")

def log(msg):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
    print(msg)

def run_standalone():
    if os.path.exists(LOG_PATH): os.remove(LOG_PATH)
    log("Standalone Sync Started...")
    
    # Simple hardcoded league mapping for critical leagues
    league_map = {
        "English Premier League": "E0",
        "Spanish LALIGA": "SP1",
        "German Bundesliga": "D1",
        "Italian Serie A": "I1",
        "French Ligue 1": "F1",
        "Turkish Süper Lig": "T1"
    }
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Target dates
    dates = ["20260318", "20260319", "20260320", "20260321", "20260322"]
    
    total = 0
    for ds in dates:
        log(f"Fetching {ds}...")
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={ds}&limit=500"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                events = data.get("events", [])
                log(f"  -> Events: {len(events)}")
                
                for ev in events:
                    if ev.get("status", {}).get("type", {}).get("name") != "STATUS_FULL_TIME": continue
                    
                    comp = ev.get("competitions", [{}])[0]
                    league_name = ev.get("league", {}).get("name")
                    
                    code = None
                    if league_name:
                        for k, v in league_map.items():
                            if k.lower() in league_name.lower():
                                code = v; break
                    
                    if not code: continue
                    
                    cursor.execute("SELECT id FROM leagues WHERE code = ?", (code,))
                    l_id = cursor.fetchone()
                    if not l_id: continue
                    
                    competitors = comp.get("competitors", [])
                    h_name, a_name, h_score, a_score = "","",0,0
                    for c in competitors:
                        if c.get("homeAway") == "home":
                            h_name, h_score = c.get("team", {}).get("name"), int(c.get("score", 0))
                        else:
                            a_name, a_score = c.get("team", {}).get("name"), int(c.get("score", 0))
                    
                    ftr = "D"
                    if h_score > a_score: ftr = "H"
                    elif a_score > h_score: ftr = "A"
                    
                    cursor.execute("""
                        INSERT INTO matches (league_id, match_date, home_team, away_team, fthg, ftag, ftr)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(league_id, match_date, home_team, away_team) DO UPDATE SET
                            fthg=excluded.fthg, ftag=excluded.ftag, ftr=excluded.ftr
                    """, (l_id[0], ev.get("date")[:10], h_name, a_name, h_score, a_score, ftr))
                    if cursor.rowcount > 0: total += 1
                
                conn.commit()
                log(f"  -> Total Added: {total}")
        except Exception as e:
            log(f"  -> Error: {e}")
            
    conn.close()
    log(f"DONE. Total: {total}")

if __name__ == "__main__":
    run_standalone()

from database import Database
from espn_fetcher import EspnResultsFetcher
import json
import os

def diagnose():
    db = Database()
    fetcher = EspnResultsFetcher()
    
    # 1. Check League Mapping
    print("Checking specific date from ESPN: 2026-03-21")
    matches = fetcher.fetch_results_for_date("20260321")
    print(f"Total events found by fetcher: {len(matches)}")
    
    if matches:
        # Check if they map to any of our leagues
        mapping_file = "data/espn_league_mappings.json"
        with open(mapping_file, "r") as f:
            league_map = json.load(f)
            
        mapped_count = 0
        for m in matches:
            espn_league = m.get("league_name")
            target_code = league_map.get(espn_league)
            if not target_code:
                # Substring check
                for k, v in league_map.items():
                    if k in espn_league or espn_league in k:
                        target_code = v
                        break
            if target_code:
                mapped_count += 1
                # print(f"  Match! {espn_league} -> {target_code}")
            else:
                # print(f"  Miss: {espn_league}")
                pass
        
        print(f"Mapped matches ready for import: {mapped_count}")
        
        # 2. Try an import test
        print("Running test import for these matches...")
        import_count = db.import_espn_matches(matches)
        print(f"Successfully imported/updated: {import_count}")
    
    # 3. Last 5 matches in DB
    conn = db.get_connection()
    res = conn.execute("SELECT match_date, home_team, away_team FROM matches ORDER BY match_date DESC LIMIT 5").fetchall()
    print("\nLast 5 matches in Database:")
    for r in res:
        print(f"  {r[0]} | {r[1]} vs {r[2]}")

if __name__ == "__main__":
    diagnose()

from database import Database
from api_data_org import FootballDataOrgAPI
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sync_all():
    from config import SOURCES
    api_key = SOURCES.get("football-data-org", {}).get("api_key")
    
    db = Database()
    api = FootballDataOrgAPI(api_key=api_key)

    
    print("--- 1. CSV Import (football-data.co.uk) ---")
    # Bu adim zaten AutoResearcher tarafından yapılıyor olabilir ama test için:
    # db.import_all_csvs()
    
    print("\n--- 2. API Sync (football-data.org) ---")
    print("Fetching recent matches from API...")
    recent_matches = api.fetch_recent_matches(days=3)
    
    if recent_matches:
        print(f"Fetched {len(recent_matches)} matches via API.")
        count = db.import_api_matches(recent_matches)
        print(f"Imported/Updated {count} matches from API results.")
    else:
        print("No recent matches found or API limit reached.")

    print("\n--- 3. Check for Duplicates ---")
    conn = db.get_connection()
    # Aynı gün, aynı takımlar arasında birden fazla kayıt var mı?
    dup_query = """
        SELECT match_date, home_team, away_team, COUNT(*) as count 
        FROM matches 
        GROUP BY match_date, home_team, away_team 
        HAVING count > 1
    """
    dups = conn.execute(dup_query).fetchall()
    if not dups:
        print("✅ SUCCESS: No duplicate matches found after merge.")
    else:
        print(f"❌ WARNING: {len(dups)} duplicate matches found!")
        for d in dups:
            print(f"   Duplicate: {d['match_date']} {d['home_team']} vs {d['away_team']} ({d['count']} occurrences)")

if __name__ == "__main__":
    sync_all()

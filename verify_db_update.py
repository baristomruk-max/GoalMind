from database import Database
from datetime import datetime, timedelta
import logging

def verify():
    db = Database()
    conn = db.get_connection()
    
    print("=== Veritabanı Güncelleme Doğrulaması ===\n")
    
    # 1. Toplam Maç Sayısı
    total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    print(f"Toplam Maç Sayısı: {total}")
    
    # 2. Son 7 Günlük Maç Sayısı
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = conn.execute("SELECT COUNT(*) FROM matches WHERE match_date >= ?", (seven_days_ago,)).fetchone()[0]
    print(f"Son 7 Günde Eklenen/Güncellenen Maç Sayısı: {recent}")
    
    # 3. Lig Bazlı Son Maç Tarihleri
    print("\nLig Bazlı En Güncel Maç Tarihleri (Son 5 Lig):")
    leagues = conn.execute("""
        SELECT l.name, MAX(m.match_date) as last_date, COUNT(m.id) as match_count
        FROM matches m 
        JOIN leagues l ON m.league_id = l.id 
        GROUP BY l.name 
        ORDER BY last_date DESC 
        LIMIT 5
    """).fetchall()
    
    for l in leagues:
        print(f"  - {l['name']}: {l['last_date']} ({l['match_count']} toplam maç)")
        
    # 4. En Son Eklenen 5 Maçın Detayı
    print("\nEn Son Eklenen 5 Maç:")
    recent_matches = conn.execute("""
        SELECT l.name, m.match_date, m.home_team, m.away_team, m.fthg, m.ftag 
        FROM matches m 
        JOIN leagues l ON m.league_id = l.id 
        WHERE m.match_date IS NOT NULL
        ORDER BY m.match_date DESC, m.id DESC 
        LIMIT 5
    """).fetchall()
    
    for m in recent_matches:
        print(f"  [{m['match_date']}] {m['name']}: {m['home_team']} {m['fthg']}-{m['ftag']} {m['away_team']}")

if __name__ == "__main__":
    verify()

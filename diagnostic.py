"""Quick diagnostic script."""
import sqlite3

DB = 'E:/KODLAMA/BARİS YAPAY ZEKA/FootballData/football_data.db'
conn = sqlite3.connect(DB)
c = conn.cursor()

# Total predictions
c.execute('SELECT COUNT(*) FROM predictions')
total = c.fetchone()[0]
print(f'Total predictions: {total}')

# By status
c.execute('SELECT status, COUNT(*) FROM predictions GROUP BY status')
for row in c.fetchall():
    print(f'  {row[0]}: {row[1]}')

# Sample predictions with all match_dates
c.execute('SELECT DISTINCT match_date FROM predictions ORDER BY match_date DESC LIMIT 15')
print('\nRecent prediction dates:')
for r in c.fetchall():
    print(f'  {r[0]}')

# Future predictions
c.execute("SELECT match_date, home_team, away_team, predicted_result, confidence, status FROM predictions WHERE match_date >= '2026-09-03' ORDER BY match_date LIMIT 15")
rows = c.fetchall()
print(f'\nFuture predictions (>= 2026-09-03): {len(rows)}')
for r in rows:
    print(f'  {r[0]} | {r[1]} vs {r[2]} | Pred: {r[3]} ({r[4]}%) | {r[5]}')

# Pending
c.execute("SELECT COUNT(*) FROM predictions WHERE status = 'pending'")
pending = c.fetchone()[0]
print(f'\nPending predictions: {pending}')

# Team count
c.execute('SELECT COUNT(*) FROM (SELECT DISTINCT home_team FROM matches UNION SELECT DISTINCT away_team FROM matches)')
teams = c.fetchone()[0]
print(f'Unique teams in matches table: {teams}')

# Sample DB teams
c.execute('SELECT DISTINCT home_team FROM matches ORDER BY home_team LIMIT 20')
print('\nSample DB teams:')
for r in c.fetchall():
    print(f'  {r[0]}')

# Sample fixture teams
import csv
print('\nSample fixture CSV teams:')
with open('E:/KODLAMA/BARİS YAPAY ZEKA/FootballData/data/bsd_fixtures.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    count = 0
    for row in reader:
        if count < 15:
            print(f"  {row['HomeTeam']} vs {row['AwayTeam']} ({row['Date']})")
            count += 1

conn.close()

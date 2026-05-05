import logging
from database import Database
from fetcher import FootballDataFetcher

logging.basicConfig(level=logging.INFO)

print('Initializing DB...')
db = Database()
db.create_tables()
db.seed_leagues_and_seasons()

print('Testing fetcher...')
f = FootballDataFetcher()
# Yalnızca ufak bir lig/sezon tekil testi yapalım:
res = f.fetch_single('E0', '2526')
print('Fetch Result:', res)

print('Testing Import...')
imported = db.import_all_csvs()
print('Imported count:', imported)

print('Testing re-import for incremental check...')
imported2 = db.import_all_csvs()
print('Re-Imported count:', imported2)

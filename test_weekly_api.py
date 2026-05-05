import requests
import json
from datetime import datetime, timedelta

def test_weekly_api():
    url = "http://127.0.0.1:5000/api/weekly"
    print(f"Testing {url}...")
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
        
        if response.status_code != 200:
            print(f"FAILED: Status {response.status_code}")
            print(data)
            return

        print(f"SUCCESS: Received {data.get('total_scraped')} matches.")
        print(f"Mapped {data.get('total_mapped')} matches to DB.")
        
        predictions = data.get('predictions', [])
        if not predictions:
            print("WARNING: No predictions returned (might be no matches in range).")
            return

        dates = [p.get('match_date') for p in predictions]
        min_date = min(dates)
        max_date = max(dates)
        
        print(f"Date Range: {min_date} to {max_date}")
        
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        
        print(f"Expected Range: {today} to {next_week}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_weekly_api()

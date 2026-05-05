from espn_fetcher import EspnResultsFetcher
import json

def debug_espn():
    fetcher = EspnResultsFetcher()
    print("Fetching matches for 2026-03-21...")
    matches = fetcher.fetch_results_for_date("20260321")
    
    if not matches:
        print("No matches found. Checking raw response...")
        # Raw check
        import urllib.request
        url = f"{fetcher.base_url}?dates=20260321&limit=100"
        req = urllib.request.Request(url, headers=fetcher.headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            events = data.get("events", [])
            print(f"Total events in raw response: {len(events)}")
            if events:
                first = events[0]
                status = first.get("status", {}).get("type", {}).get("name")
                print(f"First event status: {status}")
                comp = first.get("competitions", [{}])[0]
                headline = comp.get("notes", [{}])[0].get("headline") if comp.get("notes") else "N/A"
                print(f"First event league headline: {headline}")
                league_name = first.get("league", {}).get("name", "N/A")
                print(f"First event league name: {league_name}")
    else:
        print(f"Found {len(matches)} processed matches.")
        for m in matches[:3]:
            print(f"  {m['league_name']}: {m['home_team']} vs {m['away_team']}")

if __name__ == "__main__":
    debug_espn()

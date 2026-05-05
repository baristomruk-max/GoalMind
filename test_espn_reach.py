from espn_fetcher import EspnResultsFetcher
import json

def test():
    fetcher = EspnResultsFetcher()
    date_str = "20260321"
    print(f"Testing ESPN fetch for {date_str}...")
    matches = fetcher.fetch_results_for_date(date_str)
    print(f"Matches found: {len(matches)}")
    if matches:
        print("First 2 matches:")
        print(json.dumps(matches[:2], indent=2))
    
    # Herhangi bir lig ismi dönüyor mu kontrol et
    leagues = set(m.get('league_name') for m in matches if m.get('league_name'))
    print(f"Leagues identified: {leagues}")

if __name__ == "__main__":
    test()

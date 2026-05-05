import urllib.request
import json

url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates=20260321&limit=10"
headers = {"User-Agent": "Mozilla/5.0"}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode('utf-8'))
    with open("espn_raw_sample.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
print("Saved espn_raw_sample.json")

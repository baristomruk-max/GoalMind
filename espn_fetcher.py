import urllib.request
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class EspnResultsFetcher:
    """ESPN'in gizli API'si üzerinden geçmiş ve güncel maç sonuçlarını çeker."""

    def __init__(self):
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_results_for_date(self, date_str):
        """Belirli bir tarihteki (YYYYMMDD) tüm sonuçları çeker."""
        # date_str formatı: YYYYMMDD
        url = f"{self.base_url}?dates={date_str}&limit=1000"
        
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode('utf-8'))
                return self._parse_espn_events(data.get("events", []))
        except Exception as e:
            logger.error(f"ESPN API hatası ({date_str}): {e}")
            return []

    def _parse_espn_events(self, events):
        """ESPN event listesini yerel DB formatına çevirir."""
        results = []
        for event in events:
            try:
                status = event.get("status", {}).get("type", {}).get("name")
                if status != "STATUS_FULL_TIME":
                    continue
                
                competition = event.get("competitions", [{}])[0]
                # ESPN Lig Kısa Adı (Örn: ENG.1, GER.1)
                league_name = competition.get("notes", [{}])[0].get("headline") if competition.get("notes") else None
                
                if not league_name:
                    # Alternatif 1: League objesi
                    league_name = event.get("league", {}).get("name")
                
                if not league_name:
                    # Alternatif 2: Season slug (Örn: 2025-26-english-premier-league)
                    slug = event.get("season", {}).get("slug")
                    if slug:
                        # "2025-26-" kısmını at ve kelimeleri büyüt
                        parts = slug.split("-")
                        if len(parts) > 2 and parts[0].isdigit() and parts[1].isdigit():
                            league_name = " ".join(parts[2:]).title()
                        else:
                            league_name = " ".join(parts).title()

                competitors = competition.get("competitors", [])
                home = None
                away = None
                for c in competitors:
                    team_name = c.get("team", {}).get("name")
                    score = c.get("score")
                    
                    # İstatistikleri Çıkar (Phase 14)
                    stats = {}
                    for s in c.get("statistics", []):
                        stats[s["name"]] = s["displayValue"]
                    
                    team_data = {
                        "name": team_name, 
                        "score": self._to_int(score),
                        "shots": self._to_int(stats.get("totalShots")),
                        "shots_on_target": self._to_int(stats.get("shotsOnTarget")),
                        "corners": self._to_int(stats.get("wonCorners")),
                        "possession": self._to_int(stats.get("possessionPct")),
                        "fouls": self._to_int(stats.get("foulsCommitted"))
                    }

                    if c.get("homeAway") == "home":
                        home = team_data
                    else:
                        away = team_data
                
                if home and away:
                    results.append({
                        "date": event.get("date")[:10],
                        "home_team": home["name"],
                        "away_team": away["name"],
                        "fthg": home["score"],
                        "ftag": away["score"],
                        "home_shots": home["shots"],
                        "away_shots": away["shots"],
                        "home_shots_on_target": home["shots_on_target"],
                        "away_shots_on_target": away["shots_on_target"],
                        "home_corners": home["corners"],
                        "away_corners": away["corners"],
                        "home_possession": home["possession"],
                        "away_possession": away["possession"],
                        "league_name": league_name,
                        "source": "espn"
                    })
            except Exception as e:
                logger.debug(f"ESPN event parse hatası: {e}")
                continue
        return results

    def _to_int(self, val):
        try:
            return int(val)
        except:
            return None

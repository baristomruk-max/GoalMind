import urllib.request
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class FootballDataOrgAPI:
    """football-data.org API üzerinden güncel maç sonuçlarını çeker."""

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.base_url = "https://api.football-data.org/v4"
        self.headers = {
            "X-Auth-Token": self.api_key
        } if self.api_key else {}

    def fetch_recent_matches(self, days=3):
        """Son X gündeki tamamlanmış maçları çeker."""
        date_to = datetime.now().strftime("%Y-%m-%d")
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        url = f"{self.base_url}/matches?dateFrom={date_from}&dateTo={date_to}&status=FINISHED"
        
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                return self._parse_matches(data.get("matches", []))
        except Exception as e:
            logger.error(f"football-data.org API hatası: {e}")
            return []

    def _parse_matches(self, matches):
        """API yanıtını yerel DB formatına yakın bir yapıya çevirir."""
        parsed = []
        for m in matches:
            try:
                # Lig kodunu eşleştirme (EPL, PD, BL1 vb.)
                league_code = m.get("competition", {}).get("code")
                
                parsed.append({
                    "league_code": league_code,
                    "date": m.get("utcDate")[:10],
                    "home_team": m.get("homeTeam", {}).get("name"),
                    "away_team": m.get("awayTeam", {}).get("name"),
                    "fthg": m.get("score", {}).get("fullTime", {}).get("home"),
                    "ftag": m.get("score", {}).get("fullTime", {}).get("away"),
                    "result": m.get("score", {}).get("winner")[0] if m.get("score", {}).get("winner") else None, # HOME_TEAM -> H
                    "source": "football-data.org"
                })
            except Exception as e:
                logger.debug(f"Maç parse hatası: {e}")
                continue
        return parsed

    def get_competitions(self):
        """Erişilebilir ligleri listeler."""
        url = f"{self.base_url}/competitions"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get("competitions", [])
        except Exception as e:
            logger.error(f"Lig listesi çekilemedi: {e}")
            return []

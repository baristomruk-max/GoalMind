"""
Football Data App - PredixSport API Scraper
============================================
PredixSport API'den tahmin verilerini çeker.
200 istek/ay hakkı var - dikkatli kullan!
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from config import SOURCES

logger = logging.getLogger(__name__)

# PredixSport'ın desteklediği futbol ligleri
PREDIXSPORT_LEAGUES = {
    "serie_a": {"name": "Serie A", "country": "Italy", "bsd_id": 4},
    "premier_league": {"name": "Premier League", "country": "England", "bsd_id": 1},
    "la_liga": {"name": "La Liga", "country": "Spain", "bsd_id": 3},
    "bundesliga": {"name": "Bundesliga", "country": "Germany", "bsd_id": 5},
    "ligue_1": {"name": "Ligue 1", "country": "France", "bsd_id": 6},
    "championship": {"name": "Championship", "country": "England", "bsd_id": 12},
    "league_one": {"name": "League One", "country": "England", "bsd_id": None},
    "league_two": {"name": "League Two", "country": "England", "bsd_id": None},
    "segunda_division": {"name": "Segunda División", "country": "Spain", "bsd_id": 38},
    "ligue_2": {"name": "Ligue 2", "country": "France", "bsd_id": None},
    "bundesliga_2": {"name": "2. Bundesliga", "country": "Germany", "bsd_id": None},
    "serie_b": {"name": "Serie B", "country": "Italy", "bsd_id": None},
}


class PredixSportScraper:
    """PredixSport API ile tahmin verilerini çeken scraper."""

    def __init__(self):
        predix_config = SOURCES.get("predixsport", {})
        self.api_key = predix_config.get("api_key", "")
        self.base_url = predix_config.get("base_url", "https://api.predixsport.com/v1")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "FootballDataApp/1.0",
        }
        self._request_count = 0

    def _http_get(self, path):
        """HTTP GET isteği gönderir (istek sayar)."""
        if not self.api_key:
            logger.warning("PredixSport API anahtarı tanımlı değil.")
            return None

        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self.headers)
        self._request_count += 1

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug(f"PredixSport 404: {path}")
            else:
                logger.error(f"PredixSport HTTP Hatası: {e.code} - {path}")
            return None
        except Exception as e:
            logger.error(f"PredixSport Hatası: {path} -> {e}")
            return None

    def get_request_count(self):
        """Bu oturumda yapılan istek sayısını döndürür."""
        return self._request_count

    def list_sports(self):
        """Mevcut spor dallarını listeler."""
        return self._http_get("/sports")

    def get_upcoming_predictions(self, sport="football", league=None, days=7):
        """
        Yakın tarihli tahminleri çeker.

        Args:
            sport: spor dalı (football, nba, tennis)
            league: lig kodu (serie_a, premier_league, vb.) - opsiyonel
            days: kaç günlük veri çekilecek
        """
        path = f"/predictions/{sport}/upcoming"
        params = []
        if league:
            params.append(f"league={league}")
        if days:
            params.append(f"days={days}")
        if params:
            path += "?" + "&".join(params)

        return self._http_get(path)

    def get_match_prediction(self, sport, match_id):
        """
        Tek bir maçın tahminini çeker.

        Args:
            sport: spor dalı
            match_id: maç ID'si (ör: "Girona_Sociedad_2026-05-14")
        """
        return self._http_get(f"/predictions/{sport}/{match_id}")

    def get_ratings(self, sport="football"):
        """Mevcut Elo/Glicko-2 puanlarını çeker."""
        return self._http_get(f"/ratings/{sport}")

    def get_performance(self, sport="football"):
        """Model performans verilerini çeker."""
        return self._http_get(f"/performance/{sport}")

    def get_calibration(self, sport, model_id):
        """Model kalibrasyon verilerini çeker."""
        return self._http_get(f"/calibration/{sport}/{model_id}")

    def fetch_all_football_predictions(self):
        """
        Tüm futbol liglerinin tahminlerini çeker.
        Free tier: 200 istek/ay, bu yüzden tek istekle çoklu lig çek.

        Returns:
            dict: {league_code: [match_prediction, ...]}
        """
        results = {}

        # Tek istekle tüm futbol tahminlerini çek
        data = self.get_upcoming_predictions("football")
        if not data:
            return results

        matches = data.get("matches", [])
        for pred in matches:
            league = pred.get("league", "unknown")
            if league not in results:
                results[league] = []
            results[league].append(pred)

        logger.info(f"✅ PredixSport: {len(matches)} futbol tahmini çekildi ({len(results)} lig)")
        return results

    def fetch_football_predictions_by_league(self, league_code):
        """
        Belirli bir ligin tahminlerini çeker.

        Args:
            league_code: lig kodu (serie_a, premier_league, vb.)
        """
        data = self.get_upcoming_predictions("football", league=league_code)
        if not data:
            return []

        return data.get("matches", [])

    def save_predictions_csv(self):
        """
        Tüm futbol tahminlerini CSV'ye kaydeder.
        data/predixsport_predictions.csv
        """
        import pandas as pd

        all_predictions = []
        data = self.get_upcoming_predictions("football")

        if data:
            matches = data.get("matches", [])
            for pred in matches:
                try:
                    probs = pred.get("probabilities", {})
                    all_predictions.append({
                        "match_id": pred.get("match_id", ""),
                        "league": pred.get("league", ""),
                        "home_team": pred.get("home_team", ""),
                        "away_team": pred.get("away_team", ""),
                        "prediction_date": pred.get("prediction_date", ""),
                        "home_win_prob": probs.get("home_win", ""),
                        "draw_prob": probs.get("draw", ""),
                        "away_win_prob": probs.get("away_win", ""),
                        "predicted_result": probs.get("predicted_result", ""),
                        "over_2_5_prob": probs.get("over_2_5", ""),
                        "under_2_5_prob": probs.get("under_2_5", ""),
                        "btts_yes_prob": probs.get("btts_yes", ""),
                        "btts_no_prob": probs.get("btts_no", ""),
                        "expected_corners": pred.get("expected_corners", ""),
                        "expected_shots": pred.get("expected_shots", ""),
                        "expected_spread": pred.get("expected_spread", ""),
                    })
                except (KeyError, TypeError) as e:
                    logger.debug(f"PredixSport tahmin parse hatası: {e}")
                    continue

        if all_predictions:
            df = pd.DataFrame(all_predictions)
            csv_path = os.path.join("data", "predixsport_predictions.csv")
            df.to_csv(csv_path, index=False, encoding="utf-8")
            logger.info(f"✅ PredixSport tahminleri kaydedildi: {csv_path} ({len(df)} maç)")
        else:
            logger.warning("⚠️ PredixSport: Kaydedilecek tahmin yok.")

        return all_predictions


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = PredixSportScraper()

    # Spor dallarını listele
    sports = scraper.list_sports()
    if sports:
        for s in sports.get("sports", []):
            print(f"  {s['name']}: {s.get('leagues', [])}")

    # Futbol tahminlerini çek
    predictions = scraper.fetch_all_football_predictions()
    for league, preds in predictions.items():
        print(f"\n{league}: {len(preds)} maç")
        for p in preds[:3]:
            probs = p.get("probabilities", {})
            print(f"  {p.get('home_team')} vs {p.get('away_team')}: {probs.get('predicted_result')} ({probs.get('home_win', 0):.1%})")

    # CSV'ye kaydet
    scraper.save_predictions_csv()

"""
Football Data App - Bzzoiro Sports Data API Scraper
====================================================
Bzzoiro Sports Data API kullanarak haftalık maçları ve sonuçları çeker.
Mackolik scraper'ının modern alternatifi.
"""

import os
import json
import logging
import urllib.request
import urllib.parse
import time
from datetime import datetime, timedelta
from config import SOURCES
from team_mapper import TeamMapper

logger = logging.getLogger(__name__)

# Popüler liglerin ID'leri (BSD API)
LEAGUE_IDS = {
    "Premier League": 1,
    "Liga Portugal Betclic": 2,
    "La Liga": 3,
    "Serie A": 4,
    "Bundesliga": 5,
    "Ligue 1": 6,
    "Champions League": 7,
    "Europa League": 8,
    "Brasileirão Serie A": 9,
    "Eredivisie": 10,
    "Trendyol Süper Lig": 11,
    "Championship": 12,
    "Scottish Premiership": 13,
    "Pro League (Belgium)": 14,
    "Super League (Switzerland)": 15,
    "Saudi Pro League": 17,
    "MLS": 18,
    "Liga MX Apertura": 19,
    "Liga MX Clausura": 20,
    "Parva Liga (Bulgaria)": 22,
    "Superliga (Romania)": 23,
    "Stoiximan Super League (Greece)": 24,
    "Ekstraklasa (Poland)": 25,
    "Allsvenskan (Sweden)": 26,
    "World Cup 2026": 27,
    "Nigeria Premier Football League": 28,
    "CAF Champions League": 29,
    "Africa Cup of Nations": 30,
    "Copa Libertadores": 32,
    "Copa Sudamericana": 33,
    "Brasileirão Serie B": 34,
    "Copa do Brasil": 35,
    "Liga F (Spain)": 36,
    "Segunda División (Spain)": 38,
    "FA Cup (England)": 39,
    "Carabao Cup (England)": 40,
    "Copa del Rey (Spain)": 41,
    "Coppa Italia": 42,
    "DFB Pokal (Germany)": 43,
    "Coupe de France": 44,
    "Puchar Polski": 46,
    "Tunisian Ligue 1": 47,
    "Coupe de Tunisie": 48,
    "J1 League (Japan)": 49,
    "K League 1 (South Korea)": 50,
    "Emperor Cup (Japan)": 51,
    "Chinese Super League": 52,
    "Botola Pro (Morocco)": 53,
    "Eliteserien (Norway)": 54,
    "Veikkausliiga (Finland)": 55,
    "Suomen Cup (Finland)": 56,
    "USL Championship (USA)": 57,
    "World Cup Qualification UEFA": 58,
    "World Cup Qualification CONMEBOL": 59,
    "World Cup Qualification CAF": 60,
    "World Cup Qualification AFC": 61,
    "World Cup Qualification CONCACAF": 62,
    "World Cup Qualification OFC": 63,
    "UEFA Nations League": 64,
    "CONCACAF Nations League": 65,
    "UEFA Euro 2024": 66,
    "Copa America": 67,
    "AFC Asian Cup": 68,
    "CONCACAF Gold Cup": 69,
    "NPL Queensland (Australia)": 70,
    "UEFA European U19 Championship": 71,
    "NWSL (USA)": 72,
    "Club Friendlies": 79,
}

# BSD API lig ID -> football-data.co.uk kod eşlemesi
BSD_TO_FDCODE = {
    1: "E0",    # Premier League
    2: "P1",    # Liga Portugal
    3: "SP1",   # La Liga
    4: "I1",    # Serie A
    5: "D1",    # Bundesliga
    6: "F1",    # Ligue 1
    10: "N1",   # Eredivisie
    11: "T1",   # Süper Lig
    12: "E1",   # Championship
    13: "SC0",  # Scottish Premiership
    14: "B1",   # Belgium Pro League
    15: "SWZ",  # Swiss Super League
    17: "SAU",  # Saudi Pro League
    18: "USA",  # MLS
    25: "POL",  # Ekstraklasa
    26: "SWE",  # Allsvenskan
    50: "KOR",  # K League 1
    52: "CHN",  # Chinese Super League
    54: "NOR",  # Eliteserien
    55: "FIN",  # Veikkausliiga
}


class BSDScraper:
    """Bzzoiro Sports Data API ile maç verilerini çeken scraper."""

    def __init__(self, db=None):
        self.db = db
        self.mapper = TeamMapper()
        bsd_config = SOURCES.get("bsd", {})
        self.api_key = bsd_config.get("api_key", "")
        self.base_url = bsd_config.get("base_url", "https://sports.bzzoiro.com")
        self.headers = {
            "Authorization": f"Token {self.api_key}",
            "Accept": "application/json",
        }

    def _http_get(self, url, params=None, max_retries=3):
        """HTTP GET isteği gönderir. Hatalarda yeniden dener."""
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        
        for attempt in range(max_retries):
            req = urllib.request.Request(url, headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 or e.code >= 500:
                    wait = 2 ** attempt * 3
                    logger.warning(f"BSD API HTTP {e.code} - {url} (deneme {attempt+1}/{max_retries}, {wait}s bekleniyor)")
                    time.sleep(wait)
                else:
                    logger.error(f"BSD API HTTP Hatası: {e.code} - {url}")
                    return None
            except Exception as e:
                logger.error(f"BSD API Hatası: {url} -> {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt * 2)
        
        logger.error(f"BSD API: {max_retries} deneme başarısız - {url}")
        return None

    def fetch_events(self, date_from=None, date_to=None, league_id=None, status=None, limit=200):
        """
        Belirtilen tarih aralığındaki maçları çeker.
        Sayfalama (pagination) destekler — tüm sonuçları döner.

        Args:
            date_from: Başlangıç tarihi (YYYY-MM-DD)
            date_to: Bitiş tarihi (YYYY-MM-DD)
            league_id: Lig ID'si (opsiyonel, ör: 11=Trendyol Süper Lig)
            status: Maç durumu (notstarted, inprogress, finished, vb.)
            limit: Sayfa boyutu (varsayılan 200)
        """
        if not self.api_key:
            logger.warning("BSD API anahtarı tanımlı değil.")
            return []

        # Lig ID -> İsim eşlemesi (cache)
        if not hasattr(self, '_league_map'):
            self._league_map = {}
            leagues = self.fetch_leagues()
            for l in leagues:
                self._league_map[l["id"]] = l["name"]

        # Varsayılan tarih aralığı: bugün - 14 gün
        today = datetime.now().strftime("%Y-%m-%d")
        max_future = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        if not date_from:
            date_from = today
        if not date_to:
            date_to = max_future

        # Sayfalama ile tüm sonuçları çek
        all_events = []
        offset = 0
        max_pages = 5  # Güvenlik: max 1000 maç (5 sayfa x 200)

        for page in range(max_pages):
            params = {"limit": limit, "offset": offset}
            if date_from:
                params["date_from"] = date_from
            if date_to:
                params["date_to"] = date_to
            if league_id:
                params["league_id"] = league_id
            if status:
                params["status"] = status

            logger.info(f"📡 BSD API çekiliyor: {date_from} - {date_to} (sayfa {page+1}, offset={offset})")
            data = self._http_get(f"{self.base_url}/api/v2/events/", params)

            if not data:
                break

            results = data.get("results", [])
            all_events.extend(results)

            # Sonraki sayfa var mı?
            if not data.get("next") or len(results) == 0:
                break

            offset += limit

        logger.info(f"📊 BSD API'den toplam {len(all_events)} maç çekildi ({date_from} - {date_to})")

        matches = []
        for event in all_events:
            try:
                home_team = event.get("home_team", "")
                away_team = event.get("away_team", "")

                # Takım isimlerini normalize et
                home = self.mapper.normalize(home_team) if home_team else ""
                away = self.mapper.normalize(away_team) if away_team else ""

                if not home or not away:
                    continue

                # Tarih ve saat (API field: event_date)
                start_at = event.get("event_date", "")
                match_date = ""
                match_time = ""
                if start_at:
                    try:
                        dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                        match_date = dt.strftime("%Y-%m-%d")
                        match_time = dt.strftime("%H:%M")

                        # 14 günden uzak maçları atla
                        max_date = datetime.now() + timedelta(days=14)
                        if dt.replace(tzinfo=None) > max_date:
                            continue
                    except Exception as e:
                        logger.debug(f"event_date parse hatası: {start_at} -> {e}")

                # Skor (API field: home_score, away_score - int veya None)
                home_score = event.get("home_score")
                away_score = event.get("away_score")
                fthg = home_score if home_score is not None else ""
                ftag = away_score if away_score is not None else ""

                # İlk yarı skorları (API field: home_score_ht, away_score_ht)
                home_score_ht = event.get("home_score_ht")
                away_score_ht = event.get("away_score_ht")
                hthg = home_score_ht if home_score_ht is not None else ""
                htag = away_score_ht if away_score_ht is not None else ""

                # Oranlar (varsa)
                odds = event.get("odds", {})
                b365h = odds.get("home") if isinstance(odds, dict) else ""
                b365d = odds.get("draw") if isinstance(odds, dict) else ""
                b365a = odds.get("away") if isinstance(odds, dict) else ""

                # Lig bilgisi
                league_id = event.get("league_id")
                league_name = self._league_map.get(league_id, "") if league_id else ""

                # xG Hesapla
                from xg_calculator import calculate_xg
                xg = calculate_xg(
                    home_goals=fthg if isinstance(fthg, int) else 0,
                    away_goals=ftag if isinstance(ftag, int) else 0,
                    league_name=league_name,
                )

                matches.append({
                    "event_id": event.get("id"),
                    "Div": league_name,
                    "Date": match_date,
                    "Time": match_time,
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "FTHG": fthg,
                    "FTAG": ftag,
                    "FTR": "",
                    "HTHG": hthg,
                    "HTAG": htag,
                    "B365H": b365h,
                    "B365D": b365d,
                    "B365A": b365a,
                    "Status": event.get("status", ""),
                    "league_id": event.get("league_id"),
                    "home_xg": xg["home_xg"],
                    "away_xg": xg["away_xg"],
                })
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"BSD API maç parse hatası: {e}")
                continue

        logger.info(f"✅ BSD API'den {len(matches)} maç çekildi.")
        return matches

    def fetch_upcoming_matches(self, days=14):
        """
        Gelecek günlerdeki maçları çeker.
        Tüm statülerdeki maçları çeker (notstarted, inprogress, finished).

        Args:
            days: Kaç günlük veri çekilecek (varsayılan 14)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        return self.fetch_events(date_from=today, date_to=end_date)

    def fetch_results_for_date(self, target_date):
        """
        Belirli bir tarihteki tamamlanmış maç sonuçlarını çeker.

        Args:
            target_date: Tarih (YYYY-MM-DD veya DD.MM.YYYY)
        """
        # Tarih formatınınormalize et
        if "." in target_date:
            dt = datetime.strptime(target_date, "%d.%m.%Y")
        else:
            dt = datetime.strptime(target_date, "%Y-%m-%d")

        date_str = dt.strftime("%Y-%m-%d")
        # "finished" dene, bulamazsa "FT" ile dene (API sürüme göre değişir)
        events = self.fetch_events(date_from=date_str, date_to=date_str, status="finished")
        if not events:
            events = self.fetch_events(date_from=date_str, date_to=date_str, status="FT")

        results = []
        for event in events:
            if event.get("FTHG") and event.get("FTAG"):
                results.append({
                    "home": event["HomeTeam"],
                    "away": event["AwayTeam"],
                    "fthg": str(event["FTHG"]),
                    "ftag": str(event["FTAG"]),
                })

        logger.info(f"📊 {date_str} için {len(results)} sonuç bulundu.")
        return results

    def fetch_leagues(self):
        """Mevcut ligleri çeker."""
        if not self.api_key:
            logger.warning("BSD API anahtarı tanımlı değil.")
            return []

        data = self._http_get(f"{self.base_url}/api/v2/leagues/")
        if not data:
            return []

        leagues = []
        for league in data.get("results", []):
            country = league.get("country", "")
            if isinstance(country, dict):
                country = country.get("name", "")
            leagues.append({
                "id": league.get("id"),
                "name": league.get("name"),
                "country": country,
                "slug": league.get("slug"),
            })

        logger.info(f"✅ {len(leagues)} lig bulundu.")
        return leagues

    def fetch_event_detail(self, event_id):
        """Tek bir maçın detaylı bilgilerini çeker."""
        if not self.api_key:
            return None

        data = self._http_get(f"{self.base_url}/api/v2/events/{event_id}/")
        if not data:
            return None

        return {
            "id": data.get("id"),
            "home_team": data.get("home_team"),
            "away_team": data.get("away_team"),
            "home_score": data.get("home_score"),
            "away_score": data.get("away_score"),
            "status": data.get("status"),
            "start_at": data.get("start_at"),
            "league": data.get("league_name"),
            "venue": data.get("venue"),
            "referee": data.get("referee"),
        }

    def fetch_head2head(self, event_id):
        """İki takım arasındaki geçmiş karşılaşmaları çeker."""
        if not self.api_key:
            return []

        data = self._http_get(f"{self.base_url}/api/v2/events/{event_id}/h2h/")
        if not data:
            return []

        h2h = []
        for event in data.get("results", []):
            h2h.append({
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "home_score": event.get("home_score"),
                "away_score": event.get("away_score"),
                "date": event.get("start_at"),
            })

        return h2h

    def fetch_team_stats(self, team_id):
        """Takım istatistiklerini çeker."""
        if not self.api_key:
            return None

        data = self._http_get(f"{self.base_url}/api/v2/teams/{team_id}/stats/")
        return data

    def run_weekly_pipeline(self, days=14):
        """
        Haftalık bülteni çeker ve CSV olarak kaydeder.
        Hem tüm ligleri hem de özel olarak Türk Süper Lig'i çeker.
        """
        import pandas as pd

        # 1. Tüm liglerden maçları çek
        all_matches = self.fetch_upcoming_matches(days=days)

        # 2. Türk Süper Lig ekstra çek (league_id=11)
        turkish_matches = self.fetch_events(
            date_from=datetime.now().strftime("%Y-%m-%d"),
            date_to=(datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d"),
            league_id=LEAGUE_IDS["Trendyol Süper Lig"]
        )

        # Birleştir (tekrarları kaldır)
        seen_ids = set()
        merged = []
        for m in all_matches + turkish_matches:
            eid = m.get("event_id")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                merged.append(m)

        if merged:
            df_matches = pd.DataFrame(merged)

            # Tarih formatını düzelt (DD/MM/YY formatı - notes.txt kuralları)
            def format_date(d):
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    return dt.strftime("%d/%m/%y")
                except Exception:
                    return d

            df_matches["Date"] = df_matches["Date"].apply(format_date)

            columns = [
                "Div", "Date", "Time", "HomeTeam", "AwayTeam",
                "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A", "league_id",
            ]
            for col in columns:
                if col not in df_matches.columns:
                    df_matches[col] = ""

            csv_matches = os.path.join("data", "bsd_weekly_matches.csv")
            df_matches[columns].to_csv(csv_matches, index=False, encoding="utf-8")
            logger.info(f"✅ Haftalık bülten kaydedildi: {csv_matches} ({len(merged)} maç)")
            return True
        else:
            logger.warning("⚠️ Haftalık bülten boş.")
            return False

    def save_fixtures_csv(self, days=14):
        """
        Gelecek maç programını CSV'ye kaydeder.
        Sadece tarihi ve takımları olan maçları kaydeder.
        """
        import pandas as pd

        matches = self.fetch_upcoming_matches(days=days)
        if not matches:
            logger.warning("⚠️ Kaydedilecek maç programı yok.")
            return False

        df = pd.DataFrame(matches)
        initial_count = len(df)

        # Boş tarihli veya takımsız maçları atla
        df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam"])
        df = df[df["Date"] != ""]
        df = df[df["HomeTeam"] != ""]
        df = df[df["AwayTeam"] != ""]

        dropped = initial_count - len(df)
        if dropped > 0:
            logger.warning(f"⚠️ {dropped} maç boş tarih/takım nedeniyle atlandı")

        # Tarih dağılımını logla
        if not df.empty:
            date_counts = df["Date"].value_counts().sort_index()
            logger.info(f"📅 Tarih dağılımı: {dict(date_counts.head(10))}")

        # Tarih formatını düzelt
        def format_date(d):
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return d

        df["Date"] = df["Date"].apply(format_date)

        # Gerekli sütunları seç
        columns = [
            "event_id", "Div", "Date", "Time", "HomeTeam", "AwayTeam",
            "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A", "league_id",
            "home_xg", "away_xg",
        ]
        for col in columns:
            if col not in df.columns:
                df[col] = ""

        csv_path = os.path.join("data", "bsd_fixtures.csv")
        df[columns].to_csv(csv_path, index=False, encoding="utf-8")
        logger.info(f"✅ Maç programı kaydedildi: {csv_path} ({len(df)} maç)")
        return True

    def save_results_csv(self, days=14):
        """
        Geçmiş maç sonuçlarını CSV'ye kaydeder.
        Sadece gerçekten oynanmış (skoru olan) maçları kaydeder.
        """
        import pandas as pd

        today = datetime.now().strftime("%Y-%m-%d")
        past = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        matches = self.fetch_events(date_from=past, date_to=today, status="finished")
        if not matches:
            matches = self.fetch_events(date_from=past, date_to=today, status="FT")
        if not matches:
            logger.warning("⚠️ Kaydedilecek sonuç yok.")
            return False

        df = pd.DataFrame(matches)

        # Sadece skoru olan (gerçekten oynanmış) maçları tut
        df = df.dropna(subset=["FTHG", "FTAG"])
        df = df[df["FTHG"] != ""]
        df = df[df["FTAG"] != ""]

        # Boş tarihli veya takımsız maçları atla
        df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam"])
        df = df[df["Date"] != ""]

        if df.empty:
            logger.warning("⚠️ Oynanmış maç bulunamadı.")
            return False

        # Tarih formatını düzelt
        def format_date(d):
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return d

        df["Date"] = df["Date"].apply(format_date)

        # Gerekli sütunları seç
        columns = [
            "event_id", "Div", "Date", "Time", "HomeTeam", "AwayTeam",
            "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "league_id",
            "home_xg", "away_xg",
        ]
        for col in columns:
            if col not in df.columns:
                df[col] = ""

        csv_path = os.path.join("data", "bsd_results.csv")
        df[columns].to_csv(csv_path, index=False, encoding="utf-8")
        logger.info(f"✅ Maç sonuçları kaydedildi: {csv_path} ({len(df)} maç)")

        # Import results into matches table so dashboard shows latest data
        try:
            self.db.import_bsd_csvs()
            logger.info("✅ BSD sonuçları matches tablosuna aktarıldı.")
        except Exception as e:
            logger.error(f"❌ BSD import hatası: {e}")

        return True

    def get_fixtures_from_csv(self):
        """CSV'den maç programını okur."""
        import pandas as pd

        csv_path = os.path.join("data", "bsd_fixtures.csv")
        if not os.path.exists(csv_path):
            return []

        df = pd.read_csv(csv_path)
        return df.to_dict("records")

    def get_results_from_csv(self):
        """CSV'den maç sonuçlarını okur."""
        import pandas as pd

        csv_path = os.path.join("data", "bsd_results.csv")
        if not os.path.exists(csv_path):
            return []

        df = pd.read_csv(csv_path)
        return df.to_dict("records")

    def fetch_historical_league(self, league_id, date_from=None, date_to=None, limit=200):
        """
        Belirli bir ligin geçmiş maçlarını çeker.
        CSV formatında kaydeder: data/bsd_league_{league_id}.csv
        """
        import pandas as pd

        if not self.api_key:
            logger.warning("BSD API anahtarı tanımlı değil.")
            return []

        # Lig adını al
        if not hasattr(self, '_league_map'):
            self._league_map = {}
            leagues = self.fetch_leagues()
            for l in leagues:
                self._league_map[l["id"]] = l["name"]

        league_name = self._league_map.get(league_id, f"League_{league_id}")

        # Varsayılan tarih: son 2 yıl
        if not date_from:
            date_from = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")

        # Maçları çek - "finished" dene, bulamazsa "FT" ile dene
        params = {"limit": limit, "league_id": league_id, "date_from": date_from, "date_to": date_to, "status": "finished"}
        data = self._http_get(f"{self.base_url}/api/v2/events/", params)
        if not data or not data.get("results"):
            params["status"] = "FT"
            data = self._http_get(f"{self.base_url}/api/v2/events/", params)
        if not data:
            return []

        matches = []
        for event in data.get("results", []):
            try:
                home_team = event.get("home_team", "")
                away_team = event.get("away_team", "")
                home = self.mapper.normalize(home_team) if home_team else ""
                away = self.mapper.normalize(away_team) if away_team else ""
                if not home or not away:
                    continue

                start_at = event.get("event_date", "")
                match_date = ""
                match_time = ""
                if start_at:
                    try:
                        dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                        match_date = dt.strftime("%Y-%m-%d")
                        match_time = dt.strftime("%H:%M")
                    except Exception:
                        continue

                home_score = event.get("home_score")
                away_score = event.get("away_score")
                fthg = home_score if home_score is not None else ""
                ftag = away_score if away_score is not None else ""

                # Skoru olmayanları atla (geçmiş veri olduğu için skorlu olmalı)
                if fthg == "" or ftag == "":
                    continue

                matches.append({
                    "event_id": event.get("id"),
                    "Div": league_name,
                    "Date": match_date,
                    "Time": match_time,
                    "HomeTeam": home,
                    "AwayTeam": away,
                    "FTHG": fthg,
                    "FTAG": ftag,
                    "FTR": "H" if int(fthg) > int(ftag) else ("A" if int(fthg) < int(ftag) else "D"),
                    "league_id": league_id,
                })
            except (ValueError, TypeError, KeyError) as e:
                logger.debug(f"Geçmiş maç parse hatası: {e}")
                continue

        if matches:
            df = pd.DataFrame(matches)
            csv_path = os.path.join("data", f"bsd_league_{league_id}.csv")
            df.to_csv(csv_path, index=False, encoding="utf-8")
            logger.info(f"✅ {league_name} geçmişi kaydedildi: {csv_path} ({len(df)} maç)")

        return matches

    def fetch_all_league_histories(self, league_ids=None):
        """
        Birden fazla ligin geçmiş verilerini toplu olarak çeker.
        Varsayılan olarak tüm liglerin geçmişini çeker.
        """
        if league_ids is None:
            league_ids = list(LEAGUE_IDS.values())

        total = 0
        for lid in league_ids:
            logger.info(f"📥 Lig {lid} geçmişi çekiliyor...")
            matches = self.fetch_historical_league(lid)
            total += len(matches)

        logger.info(f"✅ Toplam {len(league_ids)} ligden {total} maç çekildi.")
        return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = BSDScraper()
    scraper.run_weekly_pipeline()

"""
Football Data App - Konfigürasyon Dosyası
==========================================
football-data.co.uk veri kaynağı için lig kodları, sezonlar ve URL yapıları.
"""

import os
from datetime import datetime
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ─── Temel Ayarlar ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STANDARD_DATA_DIR = os.path.join(DATA_DIR, "standard")
EXTRA_DATA_DIR = os.path.join(DATA_DIR, "extra")
DB_PATH = os.path.join(BASE_DIR, "football_data.db")

# ─── URL Yapıları ───
BASE_URL = "https://www.football-data.co.uk/mmz4281"
EXTRA_BASE_URL = "https://www.football-data.co.uk/new"

# ─── Standart Format Ligler (mmz4281/{sezon}/{kod}.csv) ───
LEAGUES = {
    # İNGİLTERE
    "England - Premier League": "E0",
    "England - Championship": "E1",
    "England - League One": "E2",
    "England - League Two": "E3",
    "England - Conference": "EC",
    # İSPANYA
    "Spain - La Liga": "SP1",
    "Spain - Segunda": "SP2",
    # ALMANYA
    "Germany - Bundesliga": "D1",
    "Germany - 2.Bundesliga": "D2",
    # İTALYA
    "Italy - Serie A": "I1",
    "Italy - Serie B": "I2",
    # FRANSA
    "France - Ligue 1": "F1",
    "France - Ligue 2": "F2",
    # HOLLANDA
    "Netherlands - Eredivisie": "N1",
    # BELÇİKA
    "Belgium - Jupiler League": "B1",
    # PORTEKİZ
    "Portugal - Liga I": "P1",
    # TÜRKİYE
    "Turkey - Super Lig": "T1",
    # YUNANİSTAN
    "Greece - Super League": "G1",
    # İSKOÇYA
    "Scotland - Premiership": "SC0",
    "Scotland - Championship": "SC1",
    "Scotland - League One": "SC2",
    "Scotland - League Two": "SC3",
}

# ─── Sezonlar ───
def generate_seasons(start_year=15):
    """Bulunulan yıla göre sezon listesini dinamik olarak oluşturur."""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Ağustos öncesiyse (ay < 8) mevcut sezon geçen yıl başladı
    # Futbol sezonları Ağustos'ta başlar
    current_season_start = current_year - 2000
    if current_month < 8:
        current_season_start -= 1
        
    seasons = []
    for y in range(start_year, current_season_start + 1):
        seasons.append(f"{y:02d}{(y+1):02d}")
    return seasons

SEASONS = generate_seasons()

# ─── Kaynak Ayarları ───
SOURCES = {
    "football-data": {
        "base_url": "https://www.football-data.co.uk/mmz4281",
        "extra_url": "https://www.football-data.co.uk/new",
    },
    "alternative": {
        "base_url": "https://raw.githubusercontent.com/jokecamp/FootballData/master", # Örnek alternatif
    },
    "football-data-org": {
        "api_key": os.environ.get("FOOTBALL_DATA_ORG_API_KEY", ""),
        "base_url": "https://api.football-data.org/v4",

        "code_mapping": {
            "PL": "E0",   # Premier League
            "PD": "SP1",  # La Liga
            "BL1": "D1",  # Bundesliga
            "SA": "I1",   # Serie A
            "FL1": "F1",  # Ligue 1
            "DED": "N1",  # Eredivisie
            "PPL": "P1",  # Primeira Liga
            "ELC": "E1",  # Championship
        }
    },
    "bsd": {
        "api_key": os.environ.get("BSD_API_KEY", ""),
        "base_url": os.environ.get("BSD_API_BASE", "https://sports.bzzoiro.com"),
    },
    "predixsport": {
        "api_key": os.environ.get("PREDIXSPORT_API_KEY", ""),
        "base_url": os.environ.get("PREDIXSPORT_API_BASE", "https://api.predixsport.com/v1"),
    }
}


# ─── Ek Ülkeler (farklı CSV formatı: new/{kod}.csv) ───
EXTRA_LEAGUES = {
    "Argentina": "ARG",
    "Austria": "AUT",
    "Brazil": "BRA",
    "China": "CHN",
    "Colombia": "COL",
    "Croatia": "HRV",
    "Czech Republic": "CZE",
    "Denmark": "DNK",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "Finland": "FIN",
    "Hungary": "HUN",
    "India": "IND",
    "Indonesia": "IDN",
    "Ireland": "IRL",
    "Israel": "ISR",
    "Japan": "JPN",
    "Mexico": "MEX",
    "Morocco": "MAR",
    "Nigeria": "NGA",
    "Norway": "NOR",
    "Paraguay": "PAR",
    "Peru": "PER",
    "Poland": "POL",
    "Romania": "ROU",
    "Russia": "RUS",
    "Saudi Arabia": "SAU",
    "Serbia": "SRB",
    "South Korea": "KOR",
    "Sweden": "SWE",
    "Switzerland": "SWZ",
    "Tunisia": "TUN",
    "Ukraine": "UKR",
    "Uruguay": "URY",
    "USA": "USA",
    "Vietnam": "VNM",
}

# ─── Standart CSV Sütunları ───
STANDARD_COLUMNS = [
    "Div", "Date", "Time", "HomeTeam", "AwayTeam",
    "FTHG", "FTAG", "FTR",       # Full Time
    "HTHG", "HTAG", "HTR",       # Half Time
    "Referee",
    "HS", "AS",                   # Shots
    "HST", "AST",                 # Shots on Target
    "HF", "AF",                   # Fouls
    "HC", "AC",                   # Corners
    "HY", "AY",                   # Yellow Cards
    "HR", "AR",                   # Red Cards
    # Bet365 Oranları
    "B365H", "B365D", "B365A",
    # Pinnacle Oranları
    "PSH", "PSD", "PSA",
    # Market Max/Avg Oranları
    "MaxH", "MaxD", "MaxA",
    "AvgH", "AvgD", "AvgA",
]

# ─── Ekstra CSV Sütunları ───
EXTRA_COLUMNS = [
    "Country", "League", "Season", "Date", "Time",
    "Home", "Away",
    "HG", "AG", "Res",           # Goals & Result
    "PH", "PD", "PA",            # Pinnacle Odds
    "MaxH", "MaxD", "MaxA",      # Max Odds
    "AvgH", "AvgD", "AvgA",     # Average Odds
]

# ─── İndirme Ayarları ───
FETCH_CONFIG = {
    "max_workers": 5,             # Paralel indirme sayısı
    "max_retries": 3,             # Tekrar deneme sayısı
    "retry_delay": 5,             # Tekrar deneme aralığı (saniye) - 2'den 5'e çıkarıldı
    "timeout": 60,                # İstek zaman aşımı (saniye) - 30'dan 60'a çıkarıldı
    "chunk_size": 8192,           # İndirme parça boyutu
}

# ─── Flask Ayarları ───
FLASK_CONFIG = {
    "host": os.environ.get("HOST", "127.0.0.1"),
    "port": int(os.environ.get("PORT", 5000)),
    "debug": os.environ.get("FLASK_DEBUG", "False").lower() == "true",
}

"""
Football Data App - Veritabanı Katmanı
========================================
SQLite veritabanı oluşturma, CSV import ve sorgulama işlemleri.
"""

import os
import csv
import sqlite3
import logging
import json
import time
from datetime import datetime
from config import DB_PATH, STANDARD_DATA_DIR, EXTRA_DATA_DIR, LEAGUES, EXTRA_LEAGUES, SEASONS
from team_mapper import TeamMapper


logger = logging.getLogger(__name__)


class Database:
    """SQLite veritabanı yönetici sınıfı."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = None
        self.mapper = TeamMapper()


    def connect(self):
        """Veritabanı bağlantısı oluşturur."""
        # Timeout'u 30 saniyeye çekerek 'database is locked' hatalarını minimize et
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        return self.conn

    def close(self):
        """Bağlantıyı kapatır."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_connection(self):
        """Mevcut bağlantıyı döndürür veya yenisini oluşturur."""
        if self.conn is None:
            self.connect()
        return self.conn

    def create_tables(self):
        """Veritabanı tablolarını oluşturur."""
        conn = self.get_connection()
        conn.execute("BEGIN")
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leagues (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    country TEXT,
                    is_active INTEGER DEFAULT 1
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS seasons (
                    id INTEGER PRIMARY KEY,
                    league_id INTEGER,
                    name TEXT NOT NULL,
                    is_current INTEGER DEFAULT 0,
                    FOREIGN KEY (league_id) REFERENCES leagues(id)
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league_id INTEGER,
                    season_id INTEGER,
                    match_date TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    fthg INTEGER,
                    ftag INTEGER,
                    ftr TEXT,
                    -- İstatistikler
                    home_shots INTEGER,
                    away_shots INTEGER,
                    home_shots_on_target INTEGER,
                    away_shots_on_target INTEGER,
                    home_corners INTEGER,
                    away_corners INTEGER,
                    home_yellow INTEGER,
                    away_yellow INTEGER,
                    home_red INTEGER,
                    away_red INTEGER,
                    -- Oranlar 
                    b365h REAL, b365d REAL, b365a REAL,
                    psh REAL, psd REAL, psa REAL,
                    maxh REAL, maxd REAL, maxa REAL,
                    avgh REAL, avgd REAL, avga REAL,
                    -- Yeni Profesyonel Metrikler
                    referee TEXT,
                    home_possession INTEGER,
                    away_possession INTEGER,
                    home_dangerous_attacks INTEGER,
                    away_dangerous_attacks INTEGER,
                    -- Foreign Keys
                    FOREIGN KEY (league_id) REFERENCES leagues(id),
                    FOREIGN KEY (season_id) REFERENCES seasons(id)
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS predictions_history (
                    id TEXT PRIMARY KEY,
                    match_date TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    predicted_result TEXT,
                    confidence REAL,
                    goals_market TEXT,         -- JSON olarak saklanır
                    status TEXT DEFAULT 'pending',
                    league_id INTEGER,
                    model_version TEXT,
                    win_probabilities TEXT,    -- JSON as {home_win, draw, away_win}
                    tier TEXT,                 -- Platinum, Gold, Silver, Bronze
                    tier_confidence REAL,
                    advanced_metrics_json TEXT, -- 4 Layer detaylı verileri
                    actual_home_score INTEGER,
                    actual_away_score INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    config_json TEXT NOT NULL,
                    cv_score REAL,
                    train_samples INTEGER,
                    duration_sec REAL,
                    error_msg TEXT,
                    is_champion INTEGER DEFAULT 0,
                    backtest_accuracy REAL,
                    backtest_profit REAL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS accuracy_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    model_version TEXT,
                    league_id INTEGER,
                    total_predictions INTEGER,
                    correct_predictions INTEGER,
                    accuracy REAL,
                    precision REAL,
                    recall REAL,
                    f1_score REAL,
                    over_25_total INTEGER,
                    over_25_correct INTEGER,
                    over_25_accuracy REAL
                );
            """)

            # ─── Migrations (Geriye Dönük Uyumluluk) ───
            # predictions_history
            for col, col_type in [
                ("goals_market", "TEXT"), 
                ("league_id", "INTEGER"), 
                ("model_version", "TEXT"), 
                ("win_probabilities", "TEXT"),
                ("tier", "TEXT"),
                ("tier_confidence", "REAL"),
                ("advanced_metrics_json", "TEXT")
            ]:
                try:
                    conn.execute(f"ALTER TABLE predictions_history ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError: # Column already exists
                    pass
            
            # experiments
            for col, col_type in [("backtest_accuracy", "REAL"), ("backtest_profit", "REAL")]:
                try:
                    conn.execute(f"ALTER TABLE experiments ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError: # Column already exists
                    pass

            # accuracy_analysis
            for col, col_type in [("over_25_total", "INTEGER"), ("over_25_correct", "INTEGER"), ("over_25_accuracy", "REAL")]:
                try:
                    conn.execute(f"ALTER TABLE accuracy_analysis ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError: # Column already exists
                    pass

            # matches (Phase 14)
            for col, col_type in [
                ("referee", "TEXT"), 
                ("home_possession", "INTEGER"), 
                ("away_possession", "INTEGER"),
                ("home_dangerous_attacks", "INTEGER"),
                ("away_dangerous_attacks", "INTEGER")
            ]:
                try:
                    conn.execute(f"ALTER TABLE matches ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            conn.commit()
            logger.info("✅ Veritabanı tabloları oluşturuldu / güncellendi.")
        except Exception as e:
            conn.rollback()
            logger.error(f"Tablo oluşturma hatası: {e}")

    def seed_leagues_and_seasons(self):
        """Lig ve sezon verilerini ekler."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Standart ligler
        for name, code in LEAGUES.items():
            country = name.split(" - ")[0] if " - " in name else name
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO leagues (name, code, country, league_type) VALUES (?, ?, ?, ?)",
                    (name, code, country, "standard")
                )
            except sqlite3.IntegrityError:
                pass

        # Ekstra ligler
        for name, code in EXTRA_LEAGUES.items():
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO leagues (name, code, country, league_type) VALUES (?, ?, ?, ?)",
                    (name, code, name, "extra")
                )
            except sqlite3.IntegrityError:
                pass

        # Sezonlar
        for season_code in SEASONS:
            start_year = 2000 + int(season_code[:2])
            end_year = 2000 + int(season_code[2:])
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO seasons (code, start_year, end_year) VALUES (?, ?, ?)",
                    (season_code, start_year, end_year)
                )
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        logger.info("✅ Lig ve sezon verileri eklendi")

    def _parse_date(self, date_str):
        """Tarih string'ini standart formata çevirir."""
        if not date_str:
            return None
        formats = ["%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    def _safe_int(self, value):
        """Güvenli integer dönüşümü."""
        try:
            return int(float(value)) if value and str(value).strip() else None
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value):
        """Güvenli float dönüşümü."""
        try:
            return float(value) if value and str(value).strip() else None
        except (ValueError, TypeError):
            return None

    def _is_match_valid(self, home, away, match_date, hg, ag):
        """Maç verisinin geçerli olup olmadığını kontrol eder."""
        if not home or not away or not match_date:
            return False
        if hg is None or ag is None:
            return False
        return True

    def import_standard_csv(self, filepath, league_name, season_code):
        """Standart formattaki CSV dosyasını veritabanına aktarır."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # League ve season ID'lerini bul
        cursor.execute("SELECT id FROM leagues WHERE name = ?", (league_name,))
        league_row = cursor.fetchone()
        if not league_row:
            logger.warning(f"Lig bulunamadı: {league_name}")
            return 0

        cursor.execute("SELECT id FROM seasons WHERE code = ?", (season_code,))
        season_row = cursor.fetchone()
        if not season_row:
            logger.warning(f"Sezon bulunamadı: {season_code}")
            return 0

        league_id = league_row["id"]
        season_id = season_row["id"]

        count = 0
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    home = self.mapper.normalize(row.get("HomeTeam", row.get("Home", "")))
                    away = self.mapper.normalize(row.get("AwayTeam", row.get("Away", "")))

                    if not home or not away:

                        continue

                    parsed_date = self._parse_date(row.get("Date", ""))
                    hg = self._safe_int(row.get("FTHG"))
                    ag = self._safe_int(row.get("FTAG"))

                    if not self._is_match_valid(home, away, parsed_date, hg, ag):
                        continue

                    cursor.execute("""
                        INSERT INTO matches (
                            league_id, season_id, match_date, match_time,
                            home_team, away_team,
                            fthg, ftag, ftr, hthg, htag, htr,
                            referee,
                            home_shots, away_shots,
                            home_shots_target, away_shots_target,
                            home_fouls, away_fouls,
                            home_corners, away_corners,
                            home_yellow, away_yellow,
                            home_red, away_red,
                            b365h, b365d, b365a,
                            psh, psd, psa,
                            maxh, maxd, maxa,
                            avgh, avgd, avga
                        ) VALUES (
                            ?, ?, ?, ?,
                            ?, ?,
                            ?, ?, ?, ?, ?, ?,
                            ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        ON CONFLICT(league_id, match_date, home_team, away_team) DO UPDATE SET
                            season_id=excluded.season_id,
                            match_time=excluded.match_time,
                            fthg=excluded.fthg, ftag=excluded.ftag, ftr=excluded.ftr,
                            hthg=excluded.hthg, htag=excluded.htag, htr=excluded.htr,
                            referee=excluded.referee,
                            home_shots=excluded.home_shots, away_shots=excluded.away_shots,
                            home_shots_target=excluded.home_shots_target, away_shots_target=excluded.away_shots_target,
                            home_fouls=excluded.home_fouls, away_fouls=excluded.away_fouls,
                            home_corners=excluded.home_corners, away_corners=excluded.away_corners,
                            home_yellow=excluded.home_yellow, away_yellow=excluded.away_yellow,
                            home_red=excluded.home_red, away_red=excluded.away_red,
                            b365h=excluded.b365h, b365d=excluded.b365d, b365a=excluded.b365a,
                            psh=excluded.psh, psd=excluded.psd, psa=excluded.psa,
                            maxh=excluded.maxh, maxd=excluded.maxd, maxa=excluded.maxa,
                            avgh=excluded.avgh, avgd=excluded.avgd, avga=excluded.avga
                    """, (
                        league_id, season_id,
                        parsed_date,
                        row.get("Time", ""),
                        home, away,
                        hg, ag,
                        row.get("FTR", ""),
                        self._safe_int(row.get("HTHG")),
                        self._safe_int(row.get("HTAG")),
                        row.get("HTR", ""),
                        row.get("Referee", ""),
                        self._safe_int(row.get("HS")),
                        self._safe_int(row.get("AS")),
                        self._safe_int(row.get("HST")),
                        self._safe_int(row.get("AST")),
                        self._safe_int(row.get("HF")),
                        self._safe_int(row.get("AF")),
                        self._safe_int(row.get("HC")),
                        self._safe_int(row.get("AC")),
                        self._safe_int(row.get("HY")),
                        self._safe_int(row.get("AY")),
                        self._safe_int(row.get("HR")),
                        self._safe_int(row.get("AR")),
                        self._safe_float(row.get("B365H")),
                        self._safe_float(row.get("B365D")),
                        self._safe_float(row.get("B365A")),
                        self._safe_float(row.get("PSH")),
                        self._safe_float(row.get("PSD")),
                        self._safe_float(row.get("PSA")),
                        self._safe_float(row.get("MaxH")),
                        self._safe_float(row.get("MaxD")),
                        self._safe_float(row.get("MaxA")),
                        self._safe_float(row.get("AvgH")),
                        self._safe_float(row.get("AvgD")),
                        self._safe_float(row.get("AvgA")),
                    ))
                    count += 1

            conn.commit()
            logger.info(f"✅ {league_name} ({season_code}): {count} maç eklendi")
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ CSV import hatası: {filepath} - {e}")
            raise

        return count

    def import_extra_csv(self, filepath, league_name):
        """Ekstra formattaki CSV dosyasını veritabanına aktarır."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # League ID bul
        cursor.execute("SELECT id FROM leagues WHERE name = ?", (league_name,))
        league_row = cursor.fetchone()
        if not league_row:
            logger.warning(f"Lig bulunamadı: {league_name}")
            return 0

        league_id = league_row["id"]
        count = 0

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    home = self.mapper.normalize(row.get("Home", ""))
                    away = self.mapper.normalize(row.get("Away", ""))

                    if not home or not away:

                        continue

                    # Sezon bilgisi varsa eşleştir
                    season_str = row.get("Season", "")
                    season_id = None
                    if season_str:
                        cursor.execute("SELECT id FROM seasons WHERE code = ?", (season_str,))
                        season_row = cursor.fetchone()
                        if season_row:
                            season_id = season_row["id"]

                    parsed_date = self._parse_date(row.get("Date", ""))
                    res = row.get("Res", "")
                    hg = self._safe_int(row.get("HG"))
                    ag = self._safe_int(row.get("AG"))

                    if not self._is_match_valid(home, away, parsed_date, hg, ag):
                        continue

                    cursor.execute("""
                        INSERT INTO matches (
                            league_id, season_id, match_date, match_time,
                            home_team, away_team,
                            fthg, ftag, ftr,
                            psh, psd, psa,
                            maxh, maxd, maxa,
                            avgh, avgd, avga
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(league_id, match_date, home_team, away_team) DO UPDATE SET
                            season_id=excluded.season_id,
                            match_time=excluded.match_time,
                            fthg=excluded.fthg, ftag=excluded.ftag, ftr=excluded.ftr,
                            psh=excluded.psh, psd=excluded.psd, psa=excluded.psa,
                            maxh=excluded.maxh, maxd=excluded.maxd, maxa=excluded.maxa,
                            avgh=excluded.avgh, avgd=excluded.avgd, avga=excluded.avga
                    """, (
                        league_id, season_id,
                        parsed_date,
                        row.get("Time", ""),
                        home, away,
                        hg, ag, res,
                        self._safe_float(row.get("PH")),
                        self._safe_float(row.get("PD")),
                        self._safe_float(row.get("PA")),
                        self._safe_float(row.get("MaxH")),
                        self._safe_float(row.get("MaxD")),
                        self._safe_float(row.get("MaxA")),
                        self._safe_float(row.get("AvgH")),
                        self._safe_float(row.get("AvgD")),
                        self._safe_float(row.get("AvgA")),
                    ))
                    count += 1

            conn.commit()
            logger.info(f"✅ {league_name}: {count} maç eklendi")
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ CSV import hatası: {filepath} - {e}")
            raise

        return count

    def import_api_matches(self, matches):
        """API'den gelen maç listesini veritabanına aktarır."""
        from config import SOURCES
        code_mapping = SOURCES.get("football-data-org", {}).get("code_mapping", {})
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        count = 0
        updated = 0
        
        for m in matches:
            api_code = m.get("league_code")
            target_code = code_mapping.get(api_code)
            
            if not target_code:
                continue
                
            # Lig ID bul
            cursor.execute("SELECT id FROM leagues WHERE code = ?", (target_code,))
            league_row = cursor.fetchone()
            if not league_row:
                continue
            league_id = league_row["id"]
            
            # Takım isimlerini normalize et
            home = self.mapper.normalize(m.get("home_team"))
            away = self.mapper.normalize(m.get("away_team"))
            
            # Sezon ID (Mevcut yılın sezonunu bul)
            match_date = m.get("date")
            year = int(match_date[:4])
            month = int(match_date[5:7])
            season_start = year - 2000
            if month < 7: season_start -= 1
            season_code = f"{season_start:02d}{(season_start+1):02d}"
            
            cursor.execute("SELECT id FROM seasons WHERE code = ?", (season_code,))
            season_row = cursor.fetchone()
            season_id = season_row["id"] if season_row else None
            
            # Upsert
            try:
                cursor.execute("""
                    INSERT INTO matches (
                        league_id, season_id, match_date, home_team, away_team,
                        fthg, ftag, ftr
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(league_id, match_date, home_team, away_team) DO UPDATE SET
                        fthg=excluded.fthg,
                        ftag=excluded.ftag,
                        ftr=excluded.ftr
                """, (
                    league_id, season_id, match_date, home, away,
                    m.get("fthg"), m.get("ftag"), m.get("result")
                ))
                if cursor.rowcount > 0:
                    count += 1
            except Exception as e:
                logger.debug(f"API maç import hatası: {e}")
                
        conn.commit()
        logger.info(f"✅ API'den {count} maç veritabanına işlendi/güncellendi.")
        return count

    def import_espn_matches(self, matches):
        """ESPN'den gelen maç listesini veritabanına aktarır."""
        import json
        mapping_file = "data/espn_league_mappings.json"
        league_map = {}
        if os.path.exists(mapping_file):
            with open(mapping_file, "r") as f:
                league_map = json.load(f)

        conn = self.get_connection()
        cursor = conn.cursor()
        count = 0
        
        for m in matches:
            espn_league = m.get("league_name")
            target_code = league_map.get(espn_league)
            
            # Eğer mapping yoksa league_name içinde arama yap (kısmi eşleşme + case-insensitive)
            if not target_code and espn_league:
                espn_league_lower = espn_league.lower()
                for k, v in league_map.items():
                    if k.lower() in espn_league_lower or espn_league_lower in k.lower():
                        target_code = v
                        break
            
            if not target_code:
                # logger.debug(f"League mismatch: {espn_league}")
                continue
                
            cursor.execute("SELECT id FROM leagues WHERE code = ?", (target_code,))
            league_row = cursor.fetchone()
            if not league_row:
                continue
            league_id = league_row["id"]
            
            home_raw = m.get("home_team")
            away_raw = m.get("away_team")
            home = self.mapper.normalize(home_raw)
            away = self.mapper.normalize(away_raw)
            match_date = m.get("date")
            
            # Sezon bul (Standart 18.03.2026 -> 2526 sezonu gibi)
            try:
                year = int(match_date[:4])
                month = int(match_date[5:7])
                s_start = year - 2000
                if month < 7: s_start -= 1
                s_code = f"{s_start:02d}{(s_start+1):02d}"
                cursor.execute("SELECT id FROM seasons WHERE code = ?", (s_code,))
                s_row = cursor.fetchone()
                season_id = s_row["id"] if s_row else None
            except:
                season_id = None
            
            ftr = "D"
            try:
                h_score = int(m["fthg"])
                a_score = int(m["ftag"])
                if h_score > a_score: ftr = "H"
                elif a_score > h_score: ftr = "A"
            except:
                h_score, a_score, ftr = 0, 0, "D"

            try:
                cursor.execute("""
                    INSERT INTO matches (
                        league_id, season_id, match_date, home_team, away_team,
                        fthg, ftag, ftr,
                        home_shots, away_shots, home_shots_on_target, away_shots_on_target,
                        home_corners, away_corners, home_possession, away_possession
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(league_id, match_date, home_team, away_team) DO UPDATE SET
                        fthg=excluded.fthg, ftag=excluded.ftag, ftr=excluded.ftr,
                        home_shots=excluded.home_shots, away_shots=excluded.away_shots,
                        home_shots_on_target=excluded.home_shots_on_target, away_shots_on_target=excluded.away_shots_on_target,
                        home_corners=excluded.home_corners, away_corners=excluded.away_corners,
                        home_possession=excluded.home_possession, away_possession=excluded.away_possession
                """, (
                    league_id, season_id, match_date, home, away, 
                    h_score, a_score, ftr,
                    m.get("home_shots"), m.get("away_shots"),
                    m.get("home_shots_on_target"), m.get("away_shots_on_target"),
                    m.get("home_corners"), m.get("away_corners"),
                    m.get("home_possession"), m.get("away_possession")
                ))
                if cursor.rowcount > 0: 
                    count += 1
                    # Her 50 maçta bir commit ederek lock süresini azalt
                    if count % 50 == 0:
                        conn.commit()
            except Exception as e:
                logger.debug(f"Row insert error: {e}")
                continue
                
        conn.commit()
        logger.info(f"✅ ESPN Import: {count} maç güncellendi/eklendi.")
        return count




    def import_all_csvs(self):
        """Tüm indirilen CSV dosyalarını incremental olarak veritabanına aktarır."""
        total = 0

        # Standart ligler
        for league_name, league_code in LEAGUES.items():
            for season in SEASONS:
                safe_name = league_name.replace(" ", "_").replace("-", "_")
                filepath = os.path.join(STANDARD_DATA_DIR, f"{safe_name}_{season}.csv")
                if os.path.exists(filepath):
                    try:
                        count = self.import_standard_csv(filepath, league_name, season)
                        total += count
                    except Exception as e:
                        logger.error(f"❌ Import hatası: {filepath} - {e}")

        # Ekstra ligler
        for league_name, league_code in EXTRA_LEAGUES.items():
            safe_name = league_name.replace(" ", "_").replace("-", "_")
            filepath = os.path.join(EXTRA_DATA_DIR, f"{safe_name}.csv")
            if os.path.exists(filepath):
                try:
                    count = self.import_extra_csv(filepath, league_name)
                    total += count
                except Exception as e:
                    logger.error(f"❌ Import hatası: {filepath} - {e}")

        logger.info(f"🏁 Toplam {total} maç veritabanına işlendi (Incremental Update)")
        self.optimize_db()
        return total

    def optimize_db(self):
        """Veritabanı indekslerini optimize eder ve sorgu performansını artırır."""
        conn = self.get_connection()
        try:
            # PRAGMA optimize, SQLITE'ın önerilen optimizasyonudur ve hafiftir
            conn.execute("PRAGMA optimize")
            
            # VACUUM ve ANALYZE işlemleri için isolation level'ı manuel yönet
            old_isolation = conn.isolation_level
            conn.isolation_level = None
            
            # ANALYZE her zaman güvenlidir (sorgu planlarını günceller)
            try:
                conn.execute("ANALYZE")
            except:
                pass

            # VACUUM sadece başka işlem yoksa çalışır. Meşgulse atla.
            try:
                conn.execute("VACUUM")
                logger.debug("⚡ Veritabanı VACUUM (alan geri kazanımı) tamamlandı.")
            except sqlite3.OperationalError as e:
                if "statements in progress" in str(e).lower() or "locked" in str(e).lower():
                    logger.debug("⚠️ DB Meşgul: VACUUM atlandı (Sorgular devam ediyor).")
                else:
                    logger.warning(f"⚠️ VACUUM uyarısı: {e}")
            
            conn.isolation_level = old_isolation
            logger.info("✅ Veritabanı optimizasyon adımı tamamlandı.")
        except Exception as e:
            logger.error(f"⚠️ Genel optimizasyon hatası: {e}")

    # ─── Sorgulama Fonksiyonları ───

    def get_all_leagues(self):
        """Tüm ligleri döndürür."""
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT l.*, COUNT(m.id) as match_count
            FROM leagues l
            LEFT JOIN matches m ON m.league_id = l.id
            GROUP BY l.id
            ORDER BY l.country, l.name
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_league_by_id(self, league_id):
        """ID'ye göre lig bilgisini döndürür."""
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_seasons(self):
        """Tüm sezonları döndürür."""
        conn = self.get_connection()
        cursor = conn.execute("SELECT * FROM seasons ORDER BY start_year DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_matches(self, league_id=None, season_id=None, team=None, limit=50, offset=0):
        """Filtrelenmiş maçları döndürür."""
        conn = self.get_connection()
        query = """
            SELECT m.*, l.name as league_name, s.code as season_code
            FROM matches m
            JOIN leagues l ON l.id = m.league_id
            LEFT JOIN seasons s ON s.id = m.season_id
            WHERE 1=1
        """
        params = []

        if league_id:
            query += " AND m.league_id = ?"
            params.append(league_id)
        if season_id:
            query += " AND m.season_id = ?"
            params.append(season_id)
        if team:
            query += " AND (m.home_team LIKE ? OR m.away_team LIKE ?)"
            params.extend([f"%{team}%", f"%{team}%"])

        query += " ORDER BY m.match_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_team_matches(self, team_name, limit=100):
        """Bir takımın son maçlarını verimli bir şekilde döndürür (İndeksli)."""
        conn = self.get_connection()
        # Performans için indeks oluştur (Eğer yoksa)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_home ON matches(home_team)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_away ON matches(away_team)")
        
        query = """
            SELECT * FROM matches 
            WHERE home_team = ? OR away_team = ?
            ORDER BY match_date DESC LIMIT ?
        """
        cursor = conn.execute(query, (team_name, team_name, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_match_count(self, league_id=None, season_id=None):
        """Maç sayısını döndürür."""
        conn = self.get_connection()
        query = "SELECT COUNT(*) as count FROM matches WHERE 1=1"
        params = []
        if league_id:
            query += " AND league_id = ?"
            params.append(league_id)
        if season_id:
            query += " AND season_id = ?"
            params.append(season_id)
        cursor = conn.execute(query, params)
        return cursor.fetchone()["count"]

    def get_teams(self, league_id=None):
        """Takım listesini döndürür."""
        conn = self.get_connection()
        query = """
            SELECT DISTINCT team FROM (
                SELECT home_team as team FROM matches
                UNION
                SELECT away_team as team FROM matches
            )
        """
        params = []
        if league_id:
            query = """
                SELECT DISTINCT team FROM (
                    SELECT home_team as team FROM matches WHERE league_id = ?
                    UNION
                    SELECT away_team as team FROM matches WHERE league_id = ?
                )
            """
            params = [league_id, league_id]

        query += " ORDER BY team"
        cursor = conn.execute(query, params)
        return [row["team"] for row in cursor.fetchall()]

    def get_league_table(self, league_id, season_id=None):
        """Lig puan tablosunu hesaplar ve döndürür."""
        conn = self.get_connection()

        query = """
            SELECT home_team, away_team, fthg, ftag, ftr
            FROM matches
            WHERE league_id = ? AND fthg IS NOT NULL AND ftag IS NOT NULL
        """
        params = [league_id]
        if season_id:
            query += " AND season_id = ?"
            params.append(season_id)

        cursor = conn.execute(query, params)
        matches = cursor.fetchall()

        # Puan tablosu hesapla
        table = {}
        for match in matches:
            home = match["home_team"]
            away = match["away_team"]
            hg = match["fthg"]
            ag = match["ftag"]
            result = match["ftr"]

            for team in [home, away]:
                if team not in table:
                    table[team] = {
                        "team": team, "played": 0, "won": 0, "drawn": 0, "lost": 0,
                        "goals_for": 0, "goals_against": 0, "goal_diff": 0, "points": 0
                    }

            table[home]["played"] += 1
            table[away]["played"] += 1
            table[home]["goals_for"] += hg
            table[home]["goals_against"] += ag
            table[away]["goals_for"] += ag
            table[away]["goals_against"] += hg

            if result == "H":
                table[home]["won"] += 1
                table[home]["points"] += 3
                table[away]["lost"] += 1
            elif result == "A":
                table[away]["won"] += 1
                table[away]["points"] += 3
                table[home]["lost"] += 1
            elif result == "D":
                table[home]["drawn"] += 1
                table[away]["drawn"] += 1
                table[home]["points"] += 1
                table[away]["points"] += 1

        for team_data in table.values():
            team_data["goal_diff"] = team_data["goals_for"] - team_data["goals_against"]

        # Sırala: puan > averaj > atılan gol
        sorted_table = sorted(
            table.values(),
            key=lambda x: (x["points"], x["goal_diff"], x["goals_for"]),
            reverse=True
        )

        # Sıra numarası ekle
        for i, team_data in enumerate(sorted_table, 1):
            team_data["position"] = i

        return sorted_table

    def get_stats_summary(self):
        """Genel istatistik özeti."""
        conn = self.get_connection()
        stats = {}

        cursor = conn.execute("SELECT COUNT(*) as c FROM matches")
        stats["total_matches"] = cursor.fetchone()["c"]

        cursor = conn.execute("SELECT COUNT(*) as c FROM leagues")
        stats["total_leagues"] = cursor.fetchone()["c"]

        cursor = conn.execute("""
            SELECT COUNT(DISTINCT team) as c FROM (
                SELECT home_team as team FROM matches
                UNION
                SELECT away_team as team FROM matches
            )
        """)
        stats["total_teams"] = cursor.fetchone()["c"]

        cursor = conn.execute("SELECT SUM(fthg + ftag) as c FROM matches WHERE fthg IS NOT NULL")
        result = cursor.fetchone()["c"]
        stats["total_goals"] = result or 0

        if stats["total_matches"] > 0:
            stats["avg_goals"] = round(stats["total_goals"] / stats["total_matches"], 2)
        else:
            stats["avg_goals"] = 0

        cursor = conn.execute("""
            SELECT COUNT(*) as c FROM matches WHERE ftr = 'H'
        """)
        stats["home_wins"] = cursor.fetchone()["c"]

        cursor = conn.execute("SELECT COUNT(*) as c FROM matches WHERE ftr = 'D'")
        stats["draws"] = cursor.fetchone()["c"]

        cursor = conn.execute("SELECT COUNT(*) as c FROM matches WHERE ftr = 'A'")
        stats["away_wins"] = cursor.fetchone()["c"]

        return stats

    # ─── Tahmin Takip Fonksiyonları ───

    def save_prediction(self, match_id, match_date, home_team, away_team, predicted_result, confidence, 
                        league_id=None, model_version="v1.0", goals_market=None, 
                        tier=None, tier_confidence=None, advanced_metrics=None):
        """Yeni bir ML tahmini kaydeder (veya varsa günceller)."""
        self.save_predictions_batch([{
            'id': match_id,
            'match_date': match_date,
            'home_team': home_team,
            'away_team': away_team,
            'predicted_result': predicted_result,
            'confidence': confidence,
            'league_id': league_id,
            'model_version': model_version,
            'goals_market': goals_market or {},
            'tier': tier,
            'tier_confidence': tier_confidence,
            'advanced_metrics': advanced_metrics
        }])

    def save_predictions_batch(self, predictions: list):
        """Birden fazla tahmini tek bir transaction'da kaydeder (Tier ve Advanced Metrics desteğiyle)."""
        if not predictions:
            return
            
        import time
        conn = self.get_connection()
        max_retries = 5
        for attempt in range(max_retries):
            try:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")
                for p in predictions:
                    cursor.execute("""
                        INSERT INTO predictions_history 
                        (id, match_date, home_team, away_team, predicted_result, confidence, status, 
                         goals_market, win_probabilities, league_id, model_version, tier, tier_confidence, advanced_metrics_json)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            predicted_result=excluded.predicted_result,
                            confidence=excluded.confidence,
                            status='pending',
                            goals_market=excluded.goals_market,
                            win_probabilities=excluded.win_probabilities,
                            league_id=excluded.league_id,
                            model_version=excluded.model_version,
                            tier=excluded.tier,
                            tier_confidence=excluded.tier_confidence,
                            advanced_metrics_json=excluded.advanced_metrics_json
                    """, (
                        p['id'], p['match_date'], p['home_team'], p['away_team'], 
                        p['predicted_result'], p['confidence'], 
                        json.dumps(p.get('goals_market', {})),
                        json.dumps(p.get('win_probabilities', {})),
                        p.get('league_id'), p.get('model_version', 'v1.2 (Tiered)'),
                        p.get('tier'), p.get('tier_confidence'),
                        json.dumps(p.get('advanced_metrics', {}))
                    ))
                conn.commit()
                return # Başarılı
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    logger.error(f"Batch tahmin kaydetme hatası: {e}")
                    break
            except Exception as e:
                logger.error(f"Tahmin kaydetme hatası: {e}")
                try: conn.rollback()
                except: pass
                break

    def update_prediction_result(self, match_id, home_score, away_score, status):
        """Sonucu belli olmuş maçların durumunu günceller."""
        import time
        conn = self.get_connection()
        max_retries = 5
        for attempt in range(max_retries):
            try:
                conn.execute("""
                    UPDATE predictions_history
                    SET actual_home_score = ?, actual_away_score = ?, status = ?
                    WHERE id = ? AND status = 'pending'
                """, (home_score, away_score, status, match_id))
                conn.commit()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    logger.error(f"Tahmin sonuçlandırma hatası: {e}")
                    break
            except Exception as e:
                logger.error(f"Tahmin sonuçlandırma hatası: {e}")
                try: conn.rollback()
                except: pass
                break

    def get_pending_predictions(self):
        """Henüz sonuçlanmamış tahminlerin listesini ID'leri ile döndürür."""
        conn = self.get_connection()
        cursor = conn.execute("SELECT id FROM predictions_history WHERE status = 'pending'")
        return [row["id"] for row in cursor.fetchall()]

    def backfill_missing_goals_market(self, ml_predictor=None):
        """
        goals_market alanı boş olan bekleyen tahminler için Over 2.5 değerini
        ML model veya heuristik ile yeniden hesaplar ve veritabanını günceller.
        """
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT id, home_team, away_team FROM predictions_history
            WHERE status = 'pending' AND (goals_market IS NULL OR goals_market = '{}' OR goals_market = '')
        """)
        rows = cursor.fetchall()
        
        if not rows:
            logger.info("✅ Tüm bekleyen tahminlerin goals_market verisi mevcut.")
            return 0
        
        logger.info(f"🔧 {len(rows)} kayıt için goals_market yeniden hesaplanıyor...")
        updated = 0
        
        for row in rows:
            match_id = row["id"]
            home_team = row["home_team"]
            away_team = row["away_team"]
            
            goals_market = {}
            
            if ml_predictor:
                try:
                    pred = ml_predictor.predict_match_ml(home_team, away_team)
                    if pred and not pred.get("error"):
                        goals_market = pred.get("goals_market", {})
                except Exception as e:
                    logger.warning(f"Backfill ML hata ({home_team} vs {away_team}): {e}")
            
            # ML başarısız olduysa basit heuristik kullan
            if not goals_market or not goals_market.get("over_25"):
                try:
                    h_matches = self.get_team_matches(home_team, limit=50)
                    a_matches = self.get_team_matches(away_team, limit=50)
                    
                    def _avg_scored(matches, team):
                        scored = []
                        for m in matches:
                            if m.get('fthg') is not None and m.get('ftag') is not None:
                                is_home = (m['home_team'] == team)
                                scored.append(float(m['fthg']) if is_home else float(m['ftag']))
                        return sum(scored) / len(scored) if scored else 1.3  # Ortalama gol fallback
                    
                    h_avg = _avg_scored(h_matches, home_team)
                    a_avg = _avg_scored(a_matches, away_team)
                    total_exp = h_avg + a_avg
                    over_25_prob = min(99.0, max(5.0, (total_exp / 4.0) * 100))
                    
                    goals_market = {
                        "over_25": round(over_25_prob, 1),
                        "under_25": round(100.0 - over_25_prob, 1),
                        "expected_total_goals": round(total_exp, 2)
                    }
                except Exception as e:
                    logger.warning(f"Backfill heuristik hata ({home_team} vs {away_team}): {e}")
                    goals_market = {"over_25": 50.0, "under_25": 50.0, "expected_total_goals": 2.5}
            
            # Güncelle
            try:
                # Verinin her zaman dict olmasını sağla (Phase 15)
                if isinstance(goals_market, str):
                    try:
                        goals_market = json.loads(goals_market)
                    except:
                        goals_market = {}

                conn.execute(
                    "UPDATE predictions_history SET goals_market = ? WHERE id = ?",
                    (json.dumps(goals_market), match_id)
                )
                updated += 1
            except Exception as e:
                logger.error(f"goals_market güncelleme hatası ({match_id}): {e}")
        
        try:
            conn.commit()
        except Exception as e:
            logger.error(f"Backfill commit hatası: {e}")
        
        logger.info(f"✅ {updated} kayıt için goals_market güncellendi.")
        return updated

    def get_league_table(self, league_id, season_id=None):
        """Lig bazında güncel puan durumunu hesaplar."""
        conn = self.get_connection()
        query = "SELECT home_team, away_team, fthg, ftag, ftr FROM matches WHERE league_id = ?"
        params = [league_id]
        if season_id:
            query += " AND season_id = ?"
            params.append(season_id)
            
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        
        table = {}
        for row in rows:
            h, a = row['home_team'], row['away_team']
            h_score, a_score = row['fthg'], row['ftag']
            
            if h not in table: table[h] = {"team": h, "points": 0, "played": 0}
            if a not in table: table[a] = {"team": a, "points": 0, "played": 0}
            
            # Puan hesapla (Sadece skor varsa)
            if h_score is not None and a_score is not None:
                table[h]["played"] += 1
                table[a]["played"] += 1
                if h_score > a_score: table[h]["points"] += 3
                elif a_score > h_score: table[a]["points"] += 3
                else:
                    table[h]["points"] += 1
                    table[a]["points"] += 1
        return table

    def get_prediction_accuracy_stats(self):
        """Genel tahmin başarısı ve geçmiş tahminlerin detaylarını döner."""
        conn = self.get_connection()
        stats = {
            "total": 0, "won": 0, "lost": 0, "hit_rate": 0.0, 
            "over_25_total": 0, "over_25_won": 0, "over_25_rate": 0.0,
            "history": []
        }
        
        cursor = conn.execute("SELECT * FROM predictions_history ORDER BY match_date DESC, created_at DESC")
        rows = cursor.fetchall()

        for row in rows:
            mapped = dict(row)
            
            # goals_market parse
            gm_raw = mapped.get("goals_market")
            if isinstance(gm_raw, str):
                try:
                    mapped["goals_market"] = json.loads(gm_raw)
                except:
                    mapped["goals_market"] = {}
            elif gm_raw is None:
                mapped["goals_market"] = {}
                
            stats["history"].append(mapped)
            
            # 1X2 Stats
            if mapped["status"] == "won":
                stats["won"] += 1
            elif mapped["status"] == "lost":
                stats["lost"] += 1
                
            # Over 2.5 Stats
            try:
                gm = json.loads(mapped["goals_market"]) if isinstance(mapped["goals_market"], str) else (mapped["goals_market"] or {})
                o25_prob = gm.get("over_25", 0)
                if o25_prob > 65:
                    stats["over_25_total"] += 1
                    if mapped["status"] in ["won", "lost"]:
                        h_score = mapped.get("actual_home_score")
                        a_score = mapped.get("actual_away_score")
                        if h_score is not None and a_score is not None:
                            if (h_score + a_score) > 2.5:
                                stats["over_25_won"] += 1
            except:
                pass

        total_resolved = stats["won"] + stats["lost"]
        if total_resolved > 0:
            stats["total"] = total_resolved
            stats["hit_rate"] = round((stats["won"] / total_resolved) * 100, 1)
            
        if stats["over_25_total"] > 0:
            resolved_o25 = 0
            correct_o25 = 0
            for h in stats["history"]:
                if h["status"] in ["won", "lost"]:
                    try:
                        gm_raw = h.get("goals_market")
                        gm = json.loads(gm_raw) if isinstance(gm_raw, str) else (gm_raw or {})
                        if isinstance(gm, dict) and gm.get("over_25", 0) > 65:
                            resolved_o25 += 1
                            h_score = h.get("actual_home_score")
                            a_score = h.get("actual_away_score")
                            if h_score is not None and a_score is not None:
                                if (h_score + a_score) > 2.5:
                                    correct_o25 += 1
                    except: pass
            
            if resolved_o25 > 0:
                stats["over_25_rate"] = round(float(correct_o25 / resolved_o25) * 100, 1)
                stats["over_25_resolved_total"] = resolved_o25
                stats["over_25_resolved_won"] = correct_o25

        return stats

    def get_resolved_predictions_for_training(self):
        """Sonuçlanmış tahminleri eğitim setine dahil edilmek üzere getirir."""
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT 
                match_date, home_team, away_team, 
                actual_home_score as fthg, 
                actual_away_score as ftag,
                CASE 
                    WHEN actual_home_score > actual_away_score THEN 'H'
                    WHEN actual_home_score < actual_away_score THEN 'A'
                    ELSE 'D'
                END as ftr,
                NULL as b365h, NULL as b365d, NULL as b365a,
                status as prediction_status
            FROM predictions_history
            WHERE status IN ('won', 'lost')
        """)
        return [dict(row) for row in cursor.fetchall()]

    def calculate_and_save_metrics(self):
        """Çözümlenmiş tahminlerden Precision, Recall, F1 ve Accuracy hesaplayıp accuracy_analysis tablosuna yazar."""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT 
                    model_version, 
                    league_id,
                    predicted_result,
                    status,
                    goals_market,
                    actual_home_score,
                    actual_away_score
                FROM predictions_history
                WHERE status IN ('won', 'lost')
            """)
            
            rows = cursor.fetchall()
            # Gruplandırma için veri yapısı
            groups = {} # (model, league) -> metrics_dict
            
            for row in rows:
                m_v = row["model_version"]
                l_id = row["league_id"]
                key = (m_v, l_id)
                gen_key = (m_v, None) # Genel toplam için
                
                for k in [key, gen_key]:
                    if k not in groups:
                        groups[k] = {
                            "total": 0, "correct": 0, "tp": 0, "fp": 0, "fn": 0,
                            "o25_total": 0, "o25_correct": 0
                        }
                    
                    g = groups[k]
                    g["total"] += 1
                    if row["status"] == "won":
                        g["correct"] += 1
                    
                    # 1X2 Metrikleri (Home focus)
                    if row["predicted_result"] == "1":
                        if row["status"] == "won": g["tp"] += 1
                        else: g["fp"] += 1
                    elif row["actual_home_score"] > row["actual_away_score"]:
                        g["fn"] += 1
                        
                    # Over 2.5 Metrikleri
                    try:
                        gm_raw = row["goals_market"]
                        gm = json.loads(gm_raw) if isinstance(gm_raw, str) else (gm_raw or {})
                        if isinstance(gm, dict) and gm.get("over_25", 0) > 65:
                            g["o25_total"] += 1
                            h_s = row["actual_home_score"]
                            a_s = row["actual_away_score"]
                            if h_s is not None and a_s is not None:
                                if (h_s + a_s) > 2.5:
                                    g["o25_correct"] += 1
                    except:
                        pass

            for (m_v, l_id), g in groups.items():
                if g["total"] == 0: continue
                
                accuracy = round((g["correct"] / g["total"]) * 100, 2)
                precision = g["tp"] / (g["tp"] + g["fp"]) if (g["tp"] + g["fp"]) > 0 else 0.0
                recall = g["tp"] / (g["tp"] + g["fn"]) if (g["tp"] + g["fn"]) > 0 else 0.0
                f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
                
                o25_acc = round((g["o25_correct"] / g["o25_total"]) * 100, 2) if g["o25_total"] > 0 else 0.0
                
                conn.execute("""
                    INSERT INTO accuracy_analysis 
                    (model_version, league_id, total_predictions, correct_predictions, accuracy, 
                     precision, recall, f1_score, over_25_total, over_25_correct, over_25_accuracy)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (m_v, l_id, g["total"], g["correct"], accuracy, 
                      round(precision,4), round(recall,4), round(f1,4),
                      g["o25_total"], g["o25_correct"], o25_acc))
            
                
            conn.commit()
            logger.info("📊 Başarı metrikleri (Accuracy, Precision, Recall, F1) hesaplanıp DB'ye kaydedildi.")
        except Exception as e:
            logger.error(f"Metrik hesaplama hatası: {e}", exc_info=True)


    # ─── AutoResearch Deney Yönetimi ─────────────────────────────

    def save_experiment(self, result: dict) -> int:
        """Bir deney sonucunu experiments tablosuna kaydeder. Yeni kaydın ID'sini döndürür."""
        import time
        conn = self.get_connection()
        max_retries = 5
        for attempt in range(max_retries):
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO experiments (config_json, cv_score, train_samples, duration_sec, error_msg, is_champion)
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (
                    json.dumps(result.get("config", {})),
                    result.get("cv_score"),
                    result.get("train_samples"),
                    result.get("duration_sec"),
                    result.get("error"),
                ))
                conn.commit()
                last_id = cursor.lastrowid
                cursor.close()
                return last_id
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    logger.error(f"Deney kaydetme hatası: {e}")
                    break
            except Exception as e:
                logger.error(f"Deney kaydetme hatası: {e}")
                break
        return -1

    def get_experiments(self, limit: int = 200) -> list:
        """Tüm deneyleri en yeni önce sıralayarak döndürür."""
        conn = self.get_connection()
        cursor = conn.execute(
            "SELECT * FROM experiments ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def set_champion_experiment(self, exp_id: int):
        """Verilen ID'yi champion olarak işaretler, diğerlerini sıfırlar."""
        import time
        conn = self.get_connection()
        max_retries = 5
        for attempt in range(max_retries):
            try:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")
                cursor.execute("UPDATE experiments SET is_champion = 0")
                cursor.execute("UPDATE experiments SET is_champion = 1 WHERE id = ?", (exp_id,))
                conn.commit()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    logger.error(f"Champion atama hatası: {e}")
                    break
            except Exception as e:
                logger.error(f"Champion atama hatası: {e}")
                break

    def get_champion_experiment(self) -> dict | None:
        """Champion olarak işaretlenmiş deneyi döndürür."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM experiments WHERE is_champion = 1 LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            cursor.close()

    def get_best_historical_experiment(self) -> dict | None:
        """Tüm zamanların en iyi deneyini (en yüksek kâr ve doğruluk) döndürür."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Sadece gerçek (model_type içeren) ve başarılı deneyleri al
            cursor.execute("""
                SELECT * FROM experiments 
                WHERE (error_msg IS NULL OR error_msg = '') 
                  AND backtest_profit IS NOT NULL
                  AND config_json LIKE '%model_type%'
                  AND id != 128
                ORDER BY backtest_profit DESC, backtest_accuracy DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            cursor.close()

if __name__ == "__main__":
    db = Database()
    db.create_tables()
    db.seed_leagues_and_seasons()
    print("✅ Veritabanı hazır!")


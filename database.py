"""
Football Data App - Veri Yönetim Katmanı (SQLite Tabanlı)
==========================================================
CSV dosyalarını SQLite veritabanına aktaran ve yüksek performanslı
sorgulama imkanı sağlayan veri katmanı.
"""

import os
import sqlite3
import pandas as pd
import numpy as np
import logging
import json
from datetime import datetime
from contextlib import contextmanager
from config import (
    DATA_DIR, STANDARD_DATA_DIR, EXTRA_DATA_DIR, DB_PATH,
    LEAGUES, EXTRA_LEAGUES, SEASONS, STANDARD_COLUMNS, EXTRA_COLUMNS
)
from team_mapper import TeamMapper

logger = logging.getLogger(__name__)


class Database:
    """SQLite tabanlı veri yönetim sınıfı."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.mapper = TeamMapper()
        self.matches_df = pd.DataFrame()
        self._team_match_cache = {}
        self._team_match_cache_built = False

        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        self._create_tables()

    @contextmanager
    def _get_conn(self):
        """SQLite bağlantısı açar ve otomatik kapatır."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_tables(self):
        """Tabloları oluşturur."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS leagues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    country TEXT,
                    code TEXT UNIQUE
                );

                CREATE TABLE IF NOT EXISTS seasons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league_div TEXT,
                    match_date TEXT,
                    match_time TEXT,
                    home_team TEXT,
                    away_team TEXT,
                    fthg REAL,
                    ftag REAL,
                    ftr TEXT,
                    hthg REAL,
                    htag REAL,
                    htr TEXT,
                    referee TEXT,
                    home_shots REAL,
                    away_shots REAL,
                    home_shots_on_target REAL,
                    away_shots_on_target REAL,
                    home_fouls REAL,
                    away_fouls REAL,
                    home_corners REAL,
                    away_corners REAL,
                    home_yellow REAL,
                    away_yellow REAL,
                    home_red REAL,
                    away_red REAL,
                    b365h REAL,
                    b365d REAL,
                    b365a REAL,
                    psh REAL,
                    psd REAL,
                    psa REAL,
                    maxh REAL,
                    maxd REAL,
                    maxa REAL,
                    avgh REAL,
                    avgd REAL,
                    avga REAL,
                    league_id INTEGER DEFAULT 0,
                    source_file TEXT
                );

                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY,
                    match_date TEXT,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    predicted_result TEXT,
                    confidence REAL,
                    status TEXT DEFAULT 'pending',
                    league_id INTEGER,
                    model_version TEXT,
                    win_probabilities TEXT,
                    tier TEXT,
                    tier_confidence REAL,
                    advanced_metrics_json TEXT,
                    actual_home_score INTEGER,
                    actual_away_score INTEGER,
                    created_at TEXT,
                    goals_market TEXT
                );

                CREATE TABLE IF NOT EXISTS experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_json TEXT,
                    cv_score REAL,
                    train_samples INTEGER,
                    duration_sec REAL,
                    error_msg TEXT,
                    is_champion INTEGER DEFAULT 0,
                    created_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_matches_home ON matches(home_team);
                CREATE INDEX IF NOT EXISTS idx_matches_away ON matches(away_team);
                CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
                CREATE INDEX IF NOT EXISTS idx_matches_div ON matches(league_div);
                CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
                CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(match_date);
                CREATE INDEX IF NOT EXISTS idx_experiments_champion ON experiments(is_champion);
            """)

    def connect(self):
        return self

    def close(self):
        pass

    def get_connection(self):
        return self._get_conn()

    def seed_leagues_and_seasons(self):
        """Lig ve sezonları config'den veritabanına ekler."""
        with self._get_conn() as conn:
            for name, code in LEAGUES.items():
                country = name.split("-")[0].strip() if "-" in name else name
                conn.execute(
                    "INSERT OR IGNORE INTO leagues (name, country, code) VALUES (?, ?, ?)",
                    (name, country, code)
                )
            for name, code in EXTRA_LEAGUES.items():
                country = name.split("-")[0].strip() if "-" in name else name
                conn.execute(
                    "INSERT OR IGNORE INTO leagues (name, country, code) VALUES (?, ?, ?)",
                    (name, country, code)
                )
            for season in SEASONS:
                conn.execute(
                    "INSERT OR IGNORE INTO seasons (name) VALUES (?)",
                    (season,)
                )

    def import_all_csvs(self, only_latest_season=False):
        """CSV dosyalarını SQLite'a aktarır ve matches_df'i günceller."""
        logger.info("📂 CSV dosyaları SQLite'a aktarılıyor...")
        total_imported = 0

        dirs_to_scan = []
        if os.path.exists(STANDARD_DATA_DIR):
            dirs_to_scan.append(STANDARD_DATA_DIR)
        if os.path.exists(EXTRA_DATA_DIR):
            dirs_to_scan.append(EXTRA_DATA_DIR)

        with self._get_conn() as conn:
            for data_dir in dirs_to_scan:
                for filename in os.listdir(data_dir):
                    if not filename.endswith(".csv"):
                        continue
                    filepath = os.path.join(data_dir, filename)
                    count = self._import_csv_to_sqlite(conn, filepath)
                    if count > 0:
                        total_imported += count

        self.reload_data()
        logger.info(f"✅ Toplam {total_imported} maç SQLite'a aktarıldı.")

    def import_bsd_csvs(self):
        """BSD API'den çekilen CSV dosyalarını SQLite'a aktarır."""
        logger.info("📂 BSD CSV dosyaları SQLite'a aktarılıyor...")
        total_imported = 0

        if not os.path.exists(DATA_DIR):
            return

        with self._get_conn() as conn:
            for filename in os.listdir(DATA_DIR):
                if not filename.startswith("bsd_") or not filename.endswith(".csv"):
                    continue
                if filename in ("bsd_fixtures.csv", "bsd_weekly_matches.csv"):
                    continue  # Haftalık dosyalarını atla (fixtures gelecek maçlar, results artık import ediliyor)
                filepath = os.path.join(DATA_DIR, filename)
                count = self._import_csv_to_sqlite(conn, filepath)
                if count > 0:
                    total_imported += count

        self.reload_data()
        logger.info(f"✅ BSD'den {total_imported} maç SQLite'a aktarıldı.")

    def _import_csv_to_sqlite(self, conn, filepath):
        """Tek bir CSV dosyasını SQLite'a aktarır."""
        try:
            try:
                df = pd.read_csv(filepath, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, encoding="latin-1")

            if df.empty:
                return 0

            rename_map = {
                'HG': 'fthg', 'FTHG': 'fthg',
                'AG': 'ftag', 'FTAG': 'ftag',
                'Res': 'ftr', 'FTR': 'ftr',
                'Home': 'home_team', 'HomeTeam': 'home_team',
                'Away': 'away_team', 'AwayTeam': 'away_team',
                'Date': 'match_date',
                'Time': 'match_time',
                'Div': 'league_div'
            }
            df.columns = [c.strip() for c in df.columns]
            df = df.rename(columns=rename_map)

            if 'home_team' in df.columns:
                df['home_team'] = df['home_team'].apply(lambda x: self.mapper.normalize(str(x)) if pd.notna(x) else x)
            if 'away_team' in df.columns:
                df['away_team'] = df['away_team'].apply(lambda x: self.mapper.normalize(str(x)) if pd.notna(x) else x)

            if 'league_div' not in df.columns or df['league_div'].isnull().all():
                basename = os.path.basename(filepath).replace('.csv', '').replace('___', ' - ')
                code = EXTRA_LEAGUES.get(basename)
                if not code:
                    for k, v in EXTRA_LEAGUES.items():
                        if basename.startswith(k):
                            code = v
                            break
                if code:
                    df['league_div'] = code

            numeric_cols = ['fthg', 'ftag', 'HS', 'AS', 'HST', 'AST', 'HF', 'AF', 'HC', 'AC', 'HY', 'AY', 'HR', 'AR',
                            'B365H', 'B365D', 'B365A', 'PSH', 'PSD', 'PSA', 'MaxH', 'MaxD', 'MaxA', 'AvgH', 'AvgD', 'AvgA']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                else:
                    df[col] = np.nan

            final_rename = {
                'HS': 'home_shots', 'AS': 'away_shots',
                'HST': 'home_shots_on_target', 'AST': 'away_shots_on_target',
                'HF': 'home_fouls', 'AF': 'away_fouls',
                'HC': 'home_corners', 'AC': 'away_corners',
                'HY': 'home_yellow', 'AY': 'away_yellow',
                'HR': 'home_red', 'AR': 'away_red',
                'B365H': 'b365h', 'B365D': 'b365d', 'B365A': 'b365a',
                'PSH': 'psh', 'PSD': 'psd', 'PSA': 'psa',
                'MaxH': 'maxh', 'MaxD': 'maxd', 'MaxA': 'maxa',
                'AvgH': 'avgh', 'AvgD': 'avgd', 'AvgA': 'avga'
            }
            df = df.rename(columns=final_rename)

            db_cols = ['league_div', 'match_date', 'match_time', 'home_team', 'away_team',
                       'fthg', 'ftag', 'ftr', 'hthg', 'htag', 'htr', 'referee',
                       'home_shots', 'away_shots', 'home_shots_on_target', 'away_shots_on_target',
                       'home_fouls', 'away_fouls', 'home_corners', 'away_corners',
                       'home_yellow', 'away_yellow', 'home_red', 'away_red',
                       'b365h', 'b365d', 'b365a', 'psh', 'psd', 'psa',
                       'maxh', 'maxd', 'maxa', 'avgh', 'avgd', 'avga']

            for col in db_cols:
                if col not in df.columns:
                    df[col] = None

            df['league_id'] = 0
            df['source_file'] = os.path.basename(filepath)

            if 'home_team' in df.columns:
                df = df[df['home_team'].notna() & (df['home_team'] != '')]
            if df.empty:
                return 0

            existing = conn.execute(
                "SELECT COUNT(*) FROM matches WHERE source_file = ?",
                (os.path.basename(filepath),)
            ).fetchone()[0]

            if existing > 0:
                conn.execute("DELETE FROM matches WHERE source_file = ?", (os.path.basename(filepath),))

            rows = df[db_cols + ['league_id', 'source_file']].where(pd.notna(df), None).values.tolist()
            placeholders = ', '.join(['?'] * len(db_cols + ['league_id', 'source_file']))
            col_names = ', '.join(db_cols + ['league_id', 'source_file'])
            conn.executemany(f"INSERT INTO matches ({col_names}) VALUES ({placeholders})", rows)

            return len(rows)

        except Exception as e:
            logger.error(f"CSV import hatası ({filepath}): {e}")
            return 0

    def reload_data(self):
        """SQLite'dan matches_df'i yükler."""
        self._team_match_cache.clear()
        self._team_match_cache_built = False
        logger.info("📂 SQLite verileri belleğe yükleniyor...")
        try:
            with self._get_conn() as conn:
                df = pd.read_sql_query("SELECT * FROM matches", conn)

            if not df.empty:
                df['match_date'] = pd.to_datetime(df['match_date'], dayfirst=True, errors='coerce', format='mixed')
                df = df.sort_values(by='match_date', ascending=False)
                self.matches_df = df
                logger.info(f"✅ {len(df)} maç verisi yüklendi.")
            else:
                self.matches_df = pd.DataFrame()
                logger.warning("⚠️ Hiç maç verisi bulunamadı!")

        except Exception as e:
            logger.error(f"SQLite yükleme hatası: {e}")
            self.matches_df = pd.DataFrame()

    def create_tables(self):
        self._create_tables()

    # ─── Sorgulama Metodları ───

    def get_matches(self, league_id=None, season_id=None, team=None, limit=100, offset=0):
        """Maç verilerini filtreleyerek döner."""
        if self.matches_df.empty:
            return []

        df = self.matches_df.copy()

        if team:
            df = df[(df['home_team'] == team) | (df['away_team'] == team)]
        if league_id:
            pass

        df = df.iloc[offset: offset + limit]

        df['match_date'] = df['match_date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})

        return df.to_dict('records')

    def get_all_matches_df(self):
        """Tüm maçları DataFrame olarak döner (Elo eğitimi için)."""
        if self.matches_df.empty:
            return pd.DataFrame()
        return self.matches_df.copy()

    def _build_team_match_cache(self):
        """Build an in-memory index of team_name -> list of match dicts for O(1) lookup."""
        if self._team_match_cache_built or self.matches_df.empty:
            return
        df = self.matches_df.copy()
        df['match_date'] = df['match_date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        for _, row in df.iterrows():
            h = row['home_team']
            a = row['away_team']
            if h and h not in self._team_match_cache:
                self._team_match_cache[h] = []
            if a and a not in self._team_match_cache:
                self._team_match_cache[a] = []
            rec = row.to_dict()
            if h:
                self._team_match_cache[h].append(rec)
            if a:
                self._team_match_cache[a].append(rec)
        self._team_match_cache_built = True

    def get_team_matches(self, team_name, limit=50):
        self._build_team_match_cache()
        matches = self._team_match_cache.get(team_name, [])
        return matches[:limit]

    def get_teams(self, league_id=None):
        if self.matches_df.empty:
            return []
        teams = pd.concat([self.matches_df['home_team'], self.matches_df['away_team']]).unique()
        return sorted([str(t) for t in teams if pd.notna(t)])

    def get_all_leagues(self):
        try:
            with self._get_conn() as conn:
                rows = conn.execute("SELECT id, name, country, code FROM leagues ORDER BY id").fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def get_league_by_id(self, league_id):
        leagues = self.get_all_leagues()
        for l in leagues:
            if l["id"] == league_id:
                return l
        return None

    def get_stats_summary(self):
        if self.matches_df.empty:
            return {}
        df = self.matches_df[self.matches_df['ftr'].notna()]
        total = len(df)
        goals = df['fthg'].sum() + df['ftag'].sum()

        return {
            "total_matches": int(total),
            "total_leagues": len(self.get_all_leagues()),
            "total_teams": len(self.get_teams()),
            "total_goals": int(goals),
            "avg_goals": round(goals / total, 2) if total > 0 else 0,
            "home_wins": int(len(df[df['ftr'] == 'H'])),
            "draws": int(len(df[df['ftr'] == 'D'])),
            "away_wins": int(len(df[df['ftr'] == 'A']))
        }

    def get_seasons(self):
        return [{"id": i, "name": s} for i, s in enumerate(SEASONS, 1)]

    def get_league_table(self, league_id, season_id=None):
        if self.matches_df.empty:
            return {}

        df = self.matches_df[self.matches_df['ftr'].notna()].copy()
        if df.empty:
            return {}

        teams_data = {}
        for _, row in df.iterrows():
            home = row['home_team']
            away = row['away_team']

            if home not in teams_data:
                teams_data[home] = {"team": home, "mp": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0}
            if away not in teams_data:
                teams_data[away] = {"team": away, "mp": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0}

            h_goals = row.get('fthg', 0) or 0
            a_goals = row.get('ftag', 0) or 0

            teams_data[home]["mp"] += 1
            teams_data[away]["mp"] += 1
            teams_data[home]["gf"] += h_goals
            teams_data[home]["ga"] += a_goals
            teams_data[away]["gf"] += a_goals
            teams_data[away]["ga"] += h_goals

            if row['ftr'] == 'H':
                teams_data[home]["w"] += 1
                teams_data[home]["pts"] += 3
                teams_data[away]["l"] += 1
            elif row['ftr'] == 'A':
                teams_data[away]["w"] += 1
                teams_data[away]["pts"] += 3
                teams_data[home]["l"] += 1
            else:
                teams_data[home]["d"] += 1
                teams_data[away]["d"] += 1
                teams_data[home]["pts"] += 1
                teams_data[away]["pts"] += 1

        table = sorted(teams_data.values(), key=lambda x: (-x["pts"], -(x["gf"] - x["ga"]), -x["gf"]))
        for i, t in enumerate(table):
            t["position"] = i + 1

        return {"table": table}

    # ─── Tahmin Geçmişi Metodları ───

    def save_predictions_batch(self, predictions: list):
        if not predictions:
            return

        with self._get_conn() as conn:
            for pred in predictions:
                pred['created_at'] = datetime.now().isoformat()
                existing = conn.execute("SELECT id FROM predictions WHERE id = ?", (pred.get('id'),)).fetchone()
                if existing:
                    conn.execute("""
                        UPDATE predictions SET
                            match_date=?, home_team=?, away_team=?, predicted_result=?,
                            confidence=?, status=?, league_id=?, model_version=?,
                            win_probabilities=?, tier=?, tier_confidence=?,
                            advanced_metrics_json=?, actual_home_score=?, actual_away_score=?,
                            created_at=?, goals_market=?
                        WHERE id=?
                    """, (
                        pred.get('match_date'), pred.get('home_team'), pred.get('away_team'),
                        pred.get('predicted_result'), pred.get('confidence'), pred.get('status'),
                        pred.get('league_id'), pred.get('model_version'),
                        json.dumps(pred.get('win_probabilities', {})) if isinstance(pred.get('win_probabilities'), dict) else pred.get('win_probabilities'),
                        pred.get('tier'), pred.get('tier_confidence'),
                        json.dumps(pred.get('advanced_metrics', {})) if isinstance(pred.get('advanced_metrics'), dict) else pred.get('advanced_metrics_json'),
                        pred.get('actual_home_score'), pred.get('actual_away_score'),
                        pred.get('created_at'),
                        json.dumps(pred.get('goals_market', {})) if isinstance(pred.get('goals_market'), dict) else pred.get('goals_market'),
                        pred.get('id')
                    ))
                else:
                    conn.execute("""
                        INSERT INTO predictions (id, match_date, home_team, away_team, predicted_result,
                            confidence, status, league_id, model_version, win_probabilities,
                            tier, tier_confidence, advanced_metrics_json, actual_home_score,
                            actual_away_score, created_at, goals_market)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        pred.get('id'), pred.get('match_date'), pred.get('home_team'),
                        pred.get('away_team'), pred.get('predicted_result'), pred.get('confidence'),
                        pred.get('status', 'pending'), pred.get('league_id'), pred.get('model_version'),
                        json.dumps(pred.get('win_probabilities', {})) if isinstance(pred.get('win_probabilities'), dict) else pred.get('win_probabilities'),
                        pred.get('tier'), pred.get('tier_confidence'),
                        json.dumps(pred.get('advanced_metrics', {})) if isinstance(pred.get('advanced_metrics'), dict) else pred.get('advanced_metrics_json'),
                        pred.get('actual_home_score'), pred.get('actual_away_score'),
                        pred.get('created_at', datetime.now().isoformat()),
                        json.dumps(pred.get('goals_market', {})) if isinstance(pred.get('goals_market'), dict) else pred.get('goals_market')
                    ))

    def save_prediction(self, **kwargs):
        self.save_predictions_batch([kwargs])

    def get_prediction_accuracy_stats(self):
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM predictions ORDER BY match_date DESC").fetchall()
            if not rows:
                return {"total": 0, "won": 0, "lost": 0, "hit_rate": 0.0, "history": []}

            history = []
            won = 0
            lost = 0
            for row in rows:
                r = dict(row)
                for col in ['win_probabilities', 'goals_market', 'advanced_metrics_json']:
                    if r.get(col) and isinstance(r[col], str):
                        try:
                            r[col] = json.loads(r[col])
                        except (json.JSONDecodeError, TypeError):
                            r[col] = {}
                    elif r.get(col) is None:
                        r[col] = {}
                if r.get('advanced_metrics_json'):
                    r['advanced_metrics'] = r.pop('advanced_metrics_json')
                elif 'advanced_metrics_json' in r:
                    r.pop('advanced_metrics_json', None)

                if r.get('status') == 'won':
                    won += 1
                elif r.get('status') == 'lost':
                    lost += 1
                history.append(r)

        total = won + lost
        return {
            "total": int(total),
            "won": int(won),
            "lost": int(lost),
            "hit_rate": round((won / total) * 100, 1) if total > 0 else 0,
            "history": history
        }

    def update_prediction_result(self, prediction_id, home_score, away_score, status=None):
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
            if not row:
                return False

            actual = '1' if home_score > away_score else ('2' if home_score < away_score else 'X')
            pred = str(row['predicted_result'])
            final_status = status or ('won' if pred == actual else 'lost')

            conn.execute("""
                UPDATE predictions SET actual_home_score=?, actual_away_score=?, status=?
                WHERE id=?
            """, (int(home_score), int(away_score), final_status, prediction_id))
        return True

    def get_resolved_predictions_for_training(self):
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM predictions WHERE status IN ('won', 'lost')"
            ).fetchall()

        if not rows:
            return []

        df = pd.DataFrame([dict(r) for r in rows])
        df = df.rename(columns={'actual_home_score': 'fthg', 'actual_away_score': 'ftag'})
        df['ftr'] = df.apply(lambda r: 'H' if r['fthg'] > r['ftag'] else ('A' if r['fthg'] < r['ftag'] else 'D'), axis=1)
        return df.to_dict('records')

    def delete_prediction(self, prediction_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM predictions WHERE id = ?", (prediction_id,))
        return True

    def get_pending_predictions(self):
        with self._get_conn() as conn:
            rows = conn.execute("SELECT id FROM predictions WHERE status = 'pending'").fetchall()
            return [r['id'] for r in rows]

    def get_pending_predictions_full(self):
        """Bekleyen tahminlerin tüm alanlarını döner (kalibrasyon ve self-learning için gerekli)."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, match_date, home_team, away_team, predicted_result,
                          confidence, status, tier, tier_confidence, goals_market,
                          win_probabilities, advanced_metrics_json, model_version, league_id
                   FROM predictions WHERE status = 'pending'"""
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── Temizlik ───

    def cleanup_stale_pending(self, cutoff_date: str) -> int:
        """cutoff_date öncesindeki pending tahminleri temizler. Silinen satır sayısını döner."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM predictions WHERE status = 'pending' AND match_date < ?", (cutoff_date,)
            )
            if cursor.rowcount > 0:
                conn.commit()
            return cursor.rowcount

    # ─── Deney Yönetimi ───

    def save_experiment(self, result: dict) -> int:
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO experiments (config_json, cv_score, train_samples, duration_sec, error_msg, is_champion, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (
                json.dumps(result.get("config", {})),
                result.get("cv_score"),
                result.get("train_samples"),
                result.get("duration_sec"),
                result.get("error"),
                datetime.now().isoformat()
            ))
            return cursor.lastrowid

    def get_experiments(self, limit=200):
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM experiments ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def set_champion_experiment(self, exp_id: int):
        with self._get_conn() as conn:
            conn.execute("UPDATE experiments SET is_champion = 0")
            conn.execute("UPDATE experiments SET is_champion = 1 WHERE id = ?", (exp_id,))

    def get_champion_experiment(self):
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM experiments WHERE is_champion = 1 ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return self.get_best_historical_experiment()
            return dict(row)

    def get_best_historical_experiment(self):
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM experiments
                WHERE error_msg IS NULL AND cv_score IS NOT NULL
                ORDER BY cv_score DESC LIMIT 1
            """).fetchone()
            return dict(row) if row else None

    # ─── Diğer Yardımcı Metodlar ───

    def backfill_missing_goals_market(self, ml_predictor=None):
        if not ml_predictor:
            return

        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, home_team, away_team FROM predictions WHERE goals_market IS NULL OR goals_market = '{}'"
            ).fetchall()

            if not rows:
                return

            logger.info(f"🔧 {len(rows)} adet tahminin goals_market verisi dolduruluyor...")
            for row in rows:
                try:
                    pred = ml_predictor.predict_match_ml(row['home_team'], row['away_team'], league_id=row.get('league_id'), match_date=row.get('match_date'))
                    if pred and 'goals_market' in pred:
                        conn.execute(
                            "UPDATE predictions SET goals_market = ? WHERE id = ?",
                            (json.dumps(pred['goals_market']), row['id'])
                        )
                except Exception as e:
                    logger.debug(f"Goals market backfill hatası: {e}")


if __name__ == "__main__":
    db = Database()
    print("✅ SQLite tabanlı veritabanı hazır!")

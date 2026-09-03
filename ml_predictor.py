import os
import pandas as pd
import numpy as np
import logging
import joblib
import json
import time
from datetime import datetime
from database import Database

try:
    from sklearn.ensemble import RandomForestClassifier, VotingClassifier
    from xgboost import XGBClassifier
    from lightgbm import LGBMClassifier
    from sklearn.preprocessing import StandardScaler
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

logger = logging.getLogger(__name__)

class MLPredictor:
    """Makine Öğrenmesi (XGBoost, LightGBM, Random Forest) tabanlı Gelişmiş Maç Tahmin Motoru."""

    def __init__(self, db: Database):
        self.db = db
        self.models_dir = os.path.join(os.path.dirname(__file__), "models")
        os.makedirs(self.models_dir, exist_ok=True)
        
        self.models = {}
        self.scalers = {}
        self.feature_columns = {}
        self.last_loaded_time = {}
        
        self._elo_cache = None
        self._elo_cache_time = 0
        self._calibrator_cache = None
        
        # Geriye dönük uyumluluk için eski path tanımları
        self.model_path = os.path.join(self.models_dir, "general_model.pkl")
        self.scaler_path = os.path.join(self.models_dir, "general_scaler.pkl")
        self.features_path = os.path.join(self.models_dir, "general_features.pkl")
        
        if ML_AVAILABLE:
            self.load_model()
        else:
            self.last_loaded_time = {}

    def _prepare_data(self, league_id=None):
        """Lig bazlı veya genel geçmiş verilerden eğitim veri seti oluşturur."""
        limit = 10000 if os.environ.get('RENDER') else 100000
        matches = self.db.get_matches(limit=limit)
        df_historical = pd.DataFrame(matches)
        
        resolved_predictions = self.db.get_resolved_predictions_for_training()
        df_resolved = pd.DataFrame(resolved_predictions)
        
        if df_historical.empty and df_resolved.empty:
            return pd.DataFrame(), None, {}

        df = pd.concat([df_historical, df_resolved], ignore_index=True)
        
        if 'fthg' not in df.columns:
            return pd.DataFrame(), None, {}

        if league_id and 'league_div' in df.columns:
            df = df[df['league_div'] == league_id].copy()
            if len(df) < 50:
                logger.warning(f"⚠️ {league_id} ligi için yeterli veri yok ({len(df)} maç).")
                return pd.DataFrame(), None, {}

        # Eksik verileri temizle
        df = df.dropna(subset=['fthg', 'ftag', 'ftr']).copy()
        
        # Tarihe göre sırala (Eski -> Yeni)
        df['match_date'] = pd.to_datetime(df['match_date'])
        df = df.sort_values(by='match_date')

        # Hedef Değişken (1: Ev Sahibi, 0: Beraberlik, 2: Deplasman)
        df['target'] = df['ftr'].map({'H': 1, 'D': 0, 'A': 2})
        
        # Özellik Mühendisliği (Feature Engineering)
        # Takımların hareketli ortalamaları (Son 5 maç performansı vb.)
        features = []
        labels = []
        
        df['b365h'] = df['b365h'].fillna(2.0)
        df['b365d'] = df['b365d'].fillna(3.0)
        df['b365a'] = df['b365a'].fillna(2.5)
        
        team_stats = {}
        for idx, row in df.iterrows():
            if pd.isna(row['target']): continue
            home = row['home_team']
            away = row['away_team']
            
            # Daha önce oynanmışsa geçmiş istatistikleri al (Veri Sızıntısını Önlemek için)
            if home in team_stats and away in team_stats:
                h_stat = team_stats[home]
                a_stat = team_stats[away]
                
                feat = {
                    'home_avg_goals_scored': np.mean(h_stat['scored'][-10:]) if h_stat['scored'] else 1.5,
                    'home_avg_goals_conceded': np.mean(h_stat['conceded'][-10:]) if h_stat['conceded'] else 1.5,
                    'home_win_rate': np.mean(h_stat['wins'][-10:]) if h_stat['wins'] else 0.33,
                    
                    'away_avg_goals_scored': np.mean(a_stat['scored'][-10:]) if a_stat['scored'] else 1.0,
                    'away_avg_goals_conceded': np.mean(a_stat['conceded'][-10:]) if a_stat['conceded'] else 1.5,
                    'away_win_rate': np.mean(a_stat['wins'][-10:]) if a_stat['wins'] else 0.33,
                    
                    'b365h': float(row['b365h']),
                    'b365d': float(row['b365d']),
                    'b365a': float(row['b365a']),
                }

                # Gelişmiş feature'lar (FeatureEngineer)
                try:
                    from feature_engineering import FeatureEngineer
                    fe = FeatureEngineer()
                    h_matches_list = [{'scored': s, 'conceded': c, 'result': 'W' if w else 'L', 'points': 3 if w else 0,
                                       'shots': 10, 'sot': 4, 'corners': 5, 'yellow': 1.5, 'red': 0.1,
                                       'is_home': True, 'b365h': 2.0, 'b365d': 3.0, 'b365a': 2.5,
                                       'home_team': home, 'away_team': away, 'ftr': row['ftr']}
                                      for s, c, w in zip(h_stat['scored'][-20:], h_stat['conceded'][-20:], h_stat['wins'][-20:])]
                    a_matches_list = [{'scored': s, 'conceded': c, 'result': 'W' if w else 'L', 'points': 3 if w else 0,
                                       'shots': 10, 'sot': 4, 'corners': 5, 'yellow': 1.5, 'red': 0.1,
                                       'is_home': False, 'b365h': 2.0, 'b365d': 3.0, 'b365a': 2.5,
                                       'home_team': away, 'away_team': home, 'ftr': row['ftr']}
                                      for s, c, w in zip(a_stat['scored'][-20:], a_stat['conceded'][-20:], a_stat['wins'][-20:])]

                    h_adv = fe.extract_features(h_matches_list, home, opponent_name=away, is_home=True)
                    for k, v in h_adv.items():
                        feat[f'h_{k}'] = v

                    a_adv = fe.extract_features(a_matches_list, away, opponent_name=home, is_home=False)
                    for k, v in a_adv.items():
                        feat[f'a_{k}'] = v

                    for key in ['w3_ppg', 'w5_ppg', 'w10_ppg', 'w20_ppg']:
                        hk = f'h_{key}'
                        ak = f'a_{key}'
                        if hk in feat and ak in feat:
                            feat[f'diff_{key}'] = feat[hk] - feat[ak]

                    for key in ['momentum_points', 'momentum_goals', 'consistency_score']:
                        hk = f'h_{key}'
                        ak = f'a_{key}'
                        if hk in feat and ak in feat:
                            feat[f'diff_{key}'] = feat[hk] - feat[ak]
                except Exception:
                    pass

                features.append(feat)
                labels.append(row['target'])
            
            # Takım istatistiklerini güncelle
            if home not in team_stats:
                team_stats[home] = {'scored': [], 'conceded': [], 'wins': []}
            if away not in team_stats:
                team_stats[away] = {'scored': [], 'conceded': [], 'wins': []}
                
            team_stats[home]['scored'].append(row['fthg'])
            team_stats[home]['conceded'].append(row['ftag'])
            team_stats[home]['wins'].append(1 if row['ftr'] == 'H' else 0)
            
            team_stats[away]['scored'].append(row['ftag'])
            team_stats[away]['conceded'].append(row['fthg'])
            team_stats[away]['wins'].append(1 if row['ftr'] == 'A' else 0)
            
        X = pd.DataFrame(features)
        y = np.array(labels)
        return X, y, team_stats

    def train_model(self, league_id=None):
        """Lige özel veya genel Ensemble ML modelini eğitir."""
        if not ML_AVAILABLE:
            logger.error("ML kütüphaneleri eksik!")
            return False

        try:
            model_key = league_id if league_id else 'general'
            logger.info(f"🧠 Yapay Zeka modeli eğitiliyor ({model_key})...")
            
            if not league_id:
                champion = self.db.get_best_historical_experiment()
                if champion:
                    try:
                        config = json.loads(champion["config_json"])
                        return self.train_model_with_config(config)
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.warning(f"Champion config parse hatası: {e}")

            X, y, _ = self._prepare_data(league_id)
            if X.empty:
                logger.error(f"{model_key} için yeterli veri bulunamadı.")
                return False

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            clf1 = XGBClassifier(use_label_encoder=False, eval_metric='mlogloss', n_estimators=100, random_state=42)
            clf2 = LGBMClassifier(n_estimators=100, random_state=42, verbose=-1)
            clf3 = RandomForestClassifier(n_estimators=100, random_state=42)
            
            model = VotingClassifier(
                estimators=[('xgb', clf1), ('lgbm', clf2), ('rf', clf3)],
                voting='soft'
            )
            
            logger.info(f"🚀 Modeller eğitiliyor... (Lig: {model_key}, Veri: {len(X)} maç)")
            model.fit(X_scaled, y)
            
            feats = list(X.columns)

            prefix = f"{league_id}_" if league_id else "general_"
            joblib.dump(model, os.path.join(self.models_dir, f"{prefix}model.pkl"))
            joblib.dump(scaler, os.path.join(self.models_dir, f"{prefix}scaler.pkl"))
            joblib.dump(feats, os.path.join(self.models_dir, f"{prefix}features.pkl"))
            
            self.models[model_key] = model
            self.scalers[model_key] = scaler
            self.feature_columns[model_key] = feats
            self.last_loaded_time[model_key] = time.time()
            
            logger.info(f"✅ {model_key} modeli başarıyla eğitildi ve kaydedildi.")
            return True
        except Exception as e:
            logger.error(f"Eğitim hatası ({league_id}): {e}", exc_info=True)
            return False

    def train_all_leagues(self):
        """Veritabanındaki tüm ligler için ayrı ayrı model eğitir."""
        matches = self.db.get_matches()
        df = pd.DataFrame(matches)
        if 'league_div' not in df.columns: return
        leagues = df['league_div'].dropna().unique()
        logger.info(f"🌍 {len(leagues)} farklı lig bulundu. Modeller ayrı ayrı eğitilecek...")
        for l in leagues:
            self.train_model(league_id=l)
        self.train_model(league_id=None)

    def train_model_with_config(self, config: dict) -> bool:
        """
        AutoResearcher'dan gelen champion konfigürasyonu ile modeli eğitir.
        Konfigürasyon: {model_type, model_params, feature_params}
        """
        if not ML_AVAILABLE:
            return False
        try:
            from auto_researcher import _build_features, _build_model
            logger.info(f"🏆 Champion config ile eğitim: {config.get('model_type')}")

            limit = 12000 if os.environ.get('RENDER') else 120000
            matches = self.db.get_matches(limit=limit)
            resolved = self.db.get_resolved_predictions_for_training()
            import pandas as pd
            df = pd.DataFrame(matches + resolved)
            if df.empty:
                return False

            X, y, sw = _build_features(df, config.get("feature_params", {}))
            if X.empty or len(y) < 50:
                return False

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            model = _build_model(config["model_type"], config.get("model_params", {}))
            try:
                model.fit(X_scaled, y, sample_weight=sw)
            except TypeError:
                logger.debug("Model sample_weight desteklemiyor, weightsiz eğitiliyor.")
                model.fit(X_scaled, y)
            feats = list(X.columns)

            joblib.dump(model, self.model_path)
            joblib.dump(scaler, self.scaler_path)
            joblib.dump(feats, self.features_path)
            
            self.models['general'] = model
            self.scalers['general'] = scaler
            self.feature_columns['general'] = feats
            self.last_loaded_time['general'] = time.time()
            
            logger.info("✅ Champion model diske kaydedildi ve genel model olarak aktif hale getirildi.")
            return True
        except Exception as e:
            logger.error(f"Champion eğitim hatası: {e}", exc_info=True)
            return False


    def load_model(self, league_id=None):
        """İlgili ligin veya genel modeli diske kaydettiğimiz yerden yükler."""
        if not ML_AVAILABLE: return False
        try:
            model_key = league_id if league_id else 'general'
            prefix = f"{league_id}_" if league_id else "general_"
            m_path = os.path.join(self.models_dir, f"{prefix}model.pkl")
            s_path = os.path.join(self.models_dir, f"{prefix}scaler.pkl")
            f_path = os.path.join(self.models_dir, f"{prefix}features.pkl")
            
            if os.path.exists(m_path) and os.path.exists(s_path):
                self.models[model_key] = joblib.load(m_path)
                self.scalers[model_key] = joblib.load(s_path)
                self.feature_columns[model_key] = joblib.load(f_path)
                self.last_loaded_time[model_key] = time.time()
                logger.info(f"🤖 Yapay Zeka modeli yüklendi: {model_key}")
                return True
        except Exception as e:
            logger.error(f"Model yükleme hatası ({model_key}): {e}")
        return False

    def reload_if_stale(self, league_id=None):
        """Model dosyası güncellenmişse modeli yeniden yükler."""
        if not ML_AVAILABLE: return
        model_key = league_id if league_id else 'general'
        prefix = f"{league_id}_" if league_id else "general_"
        m_path = os.path.join(self.models_dir, f"{prefix}model.pkl")
        
        if os.path.exists(m_path):
            mtime = os.path.getmtime(m_path)
            last = self.last_loaded_time.get(model_key, 0)
            if mtime > last:
                logger.info(f"🔄 Yeni model dosyası algılandı ({model_key}), yeniden yükleniyor...")
                self.load_model(league_id)

    def predict_match_ml(self, home_team, away_team, league_id=None, season_id=None, match_date=None):
        """Eğitilmiş Yapay Zeka modeli ile tek maçın sonucunu tahmin eder."""
        try:
            _t0 = time.time()
            if not ML_AVAILABLE:
                return {"error": "ML kütüphaneleri yüklü değil. Gelişmiş özellikler devre dışı."}
            
            # Güncellik kontrolü
            self.reload_if_stale(league_id)
            if not league_id: self.reload_if_stale(None)
            
            model_key = league_id if (league_id and league_id in self.models) else 'general'
            
            if model_key not in self.models:
                if league_id and self.load_model(league_id):
                    model_key = league_id
                elif self.load_model(None):
                    model_key = 'general'
                else:
                    if league_id and self.train_model(league_id):
                        model_key = league_id
                    elif self.train_model(None):
                        model_key = 'general'
                    else:
                        return {"error": "Model eğitilemedi, yeterli veri yok veya XGBoost hatası."}

            _t1 = time.time()
            model = self.models[model_key]
            scaler = self.scalers[model_key]
            features_col = self.feature_columns[model_key]

            # Takım maçlarını getir (cache'li)
            h_matches_raw = self.db.get_team_matches(home_team, limit=100)
            a_matches_raw = self.db.get_team_matches(away_team, limit=100)
            _t2 = time.time()
            
            if not h_matches_raw and not a_matches_raw:
                return {"error": "Veritabanı boş veya bu takımlar için veri yok."}

            def safe_mean(lst, n=10, default=0.0):
                res = lst[:n]
                return float(np.mean(res)) if res else default

            # H2H için her iki takımın maçlarını birleştir (unique)
            all_match_ids = {}
            for m in h_matches_raw + a_matches_raw:
                all_match_ids[m.get('id', id(m))] = m
            sorted_matches = sorted(all_match_ids.values(), key=lambda x: x.get('match_date', ''), reverse=True)
            
            def get_stats(team_name, team_matches):
                stats = {
                    'scored': [], 'conceded': [], 'wins': [], 'draws': [], 
                    'goal_diffs': [], 'shots': [], 'shots_on_target': [], 'corners': [], 
                    'b365h': [], 'b365d': [], 'b365a': [],
                    'points': [], 'yellow_cards': [], 'red_cards': []
                }
                for m in team_matches:
                    if m["home_team"] == team_name or m["away_team"] == team_name:
                        is_home = (m["home_team"] == team_name)
                        if m.get('fthg') is not None and m.get('ftag') is not None:
                            gs = float(m['fthg']) if is_home else float(m['ftag'])
                            gc = float(m['ftag']) if is_home else float(m['fthg'])
                            stats['scored'].append(gs)
                            stats['conceded'].append(gc)
                            stats['goal_diffs'].append(gs - gc)
                            if m.get('ftr'):
                                stats['wins'].append(1 if (is_home and m['ftr'] == 'H') or (not is_home and m['ftr'] == 'A') else 0)
                                stats['draws'].append(1 if m['ftr'] == 'D' else 0)
                        
                        hs = m.get('home_shots') if is_home else m.get('away_shots')
                        if hs is not None: stats['shots'].append(float(hs))
                        
                        sot = m.get('home_shots_on_target') if is_home else m.get('away_shots_on_target')
                        if sot is not None: stats['shots_on_target'].append(float(sot))

                        hc = m.get('home_corners') if is_home else m.get('away_corners')
                        if hc is not None: stats['corners'].append(float(hc))
                        
                        if m.get('ftr'):
                            stats['points'].append(3 if (is_home and m['ftr'] == 'H') or (not is_home and m['ftr'] == 'A') else (1 if m['ftr'] == 'D' else 0))
                        
                        yc = m.get('home_yellow') if is_home else m.get('away_yellow')
                        if yc is not None: stats['yellow_cards'].append(float(yc))
                        rc = m.get('home_red') if is_home else m.get('away_red')
                        if rc is not None: stats['red_cards'].append(float(rc))

                    if m["home_team"] == team_name:
                        if m.get("b365h") is not None: stats["b365h"].append(float(m["b365h"]))
                        if m.get("b365d") is not None: stats["b365d"].append(float(m["b365d"]))
                        if m.get("b365a") is not None: stats["b365a"].append(float(m["b365a"]))
                return stats
            
            h_stat = get_stats(home_team, h_matches_raw)
            a_stat = get_stats(away_team, a_matches_raw)
            
            b365h = safe_mean(h_stat['b365h'], default=2.0)
            b365d = safe_mean(h_stat['b365d'], default=3.0)
            b365a = safe_mean(h_stat['b365a'], default=2.5)

            feature_dict = {
                # Eski modeller için uyumluluk
                'home_avg_goals_scored': safe_mean(h_stat['scored']),
                'home_avg_goals_conceded': safe_mean(h_stat['conceded']),
                'away_avg_goals_scored': safe_mean(a_stat['scored']),
                'away_avg_goals_conceded': safe_mean(a_stat['conceded']),
                
                # Yeni modeller (AutoResearcher) için özellikler
                'home_goals_scored': safe_mean(h_stat['scored']),
                'home_goals_conceded': safe_mean(h_stat['conceded']),
                'home_win_rate': safe_mean(h_stat['wins']),
                'home_draw_rate': safe_mean(h_stat['draws']),
                'away_goals_scored': safe_mean(a_stat['scored']),
                'away_goals_conceded': safe_mean(a_stat['conceded']),
                'away_win_rate': safe_mean(a_stat['wins']),
                'away_draw_rate': safe_mean(a_stat['draws']),
                
                # Puan ve Kartlar (Yeni Destek)
                'home_points_avg': safe_mean(h_stat['points']),
                'away_points_avg': safe_mean(a_stat['points']),
                'home_yellow_avg': safe_mean(h_stat['yellow_cards']),
                'away_yellow_avg': safe_mean(a_stat['yellow_cards']),
                'home_red_avg':    safe_mean(h_stat['red_cards']),
                'away_red_avg':    safe_mean(a_stat['red_cards']),
            }
            
            feature_dict['points_diff'] = feature_dict['home_points_avg'] - feature_dict['away_points_avg']
            feature_dict['home_form_edge'] = feature_dict['home_win_rate'] - feature_dict['away_win_rate']
            feature_dict['goal_diff_edge'] = (feature_dict['home_goals_scored'] - feature_dict['home_goals_conceded']) - (feature_dict['away_goals_scored'] - feature_dict['away_goals_conceded'])
            feature_dict['home_gd_momentum'] = safe_mean(h_stat['goal_diffs'])
            feature_dict['away_gd_momentum'] = safe_mean(a_stat['goal_diffs'])
            feature_dict['home_shots_avg'] = safe_mean(h_stat['shots'])
            feature_dict['away_shots_avg'] = safe_mean(a_stat['shots'])
            feature_dict['home_corners_avg'] = safe_mean(h_stat['corners'])
            feature_dict['away_corners_avg'] = safe_mean(a_stat['corners'])
            
            # H2H features (sorted_matches içinde birleşik veriden çek)
            h2h_matches = [m for m in sorted_matches if (m["home_team"] == home_team and m["away_team"] == away_team) or (m["home_team"] == away_team and m["away_team"] == home_team)]
            h2h_matches_recent = list(h2h_matches)[:10]
            if h2h_matches_recent:
                h2h_wins = sum([1 for m in h2h_matches_recent if (m["home_team"] == home_team and m.get("ftr") == "H") or (m["away_team"] == home_team and m.get("ftr") == "A")])
                feature_dict['h2h_home_win_rate'] = float(h2h_wins) / len(h2h_matches_recent)
            else:
                feature_dict['h2h_home_win_rate'] = 0.5
                
            feature_dict['b365h'] = float(b365h)
            feature_dict['b365d'] = float(b365d)
            feature_dict['b365a'] = float(b365a)

            # Odds-implied probabilities (vig arındırılmış)
            total_implied = (1.0/b365h + 1.0/b365d + 1.0/b365a) if b365h > 0 and b365d > 0 and b365a > 0 else 1.0
            feature_dict['odds_implied_home'] = (1.0/b365h) / total_implied if b365h > 0 else 0.33
            feature_dict['odds_implied_draw'] = (1.0/b365d) / total_implied if b365d > 0 else 0.33
            feature_dict['odds_implied_away'] = (1.0/b365a) / total_implied if b365a > 0 else 0.33
            feature_dict['odds_value_home'] = feature_dict.get('home_win_rate', 0.5) - feature_dict['odds_implied_home']
            feature_dict['odds_value_away'] = feature_dict.get('away_win_rate', 0.5) - feature_dict['odds_implied_away']

            # Elo Rating features (cached)
            try:
                from elo import EloSystem
                now_ts = time.time()
                if self._elo_cache is None or (now_ts - self._elo_cache_time) > 300:
                    self._elo_cache = EloSystem(self.db)
                    self._elo_cache_time = now_ts
                elo = self._elo_cache
                elo_features = elo.get_features(home_team, away_team)
                feature_dict.update(elo_features)
            except Exception:
                feature_dict['home_elo'] = 1500.0
                feature_dict['away_elo'] = 1500.0
                feature_dict['elo_diff'] = 0.0

            # ─── Gelişmiş Feature Engineering (100+ feature) ───
            try:
                from feature_engineering import FeatureEngineer
                fe = FeatureEngineer()

                h_adv = fe.extract_features(h_matches_raw, home_team, opponent_name=away_team, is_home=True)
                for k, v in h_adv.items():
                    feature_dict[f'h_{k}'] = v

                a_adv = fe.extract_features(a_matches_raw, away_team, opponent_name=home_team, is_home=False)
                for k, v in a_adv.items():
                    feature_dict[f'a_{k}'] = v

                # Ev/deplasman farkı feature'ları
                for key in ['w3_ppg', 'w5_ppg', 'w10_ppg', 'w20_ppg']:
                    hk = f'h_{key}'
                    ak = f'a_{key}'
                    if hk in feature_dict and ak in feature_dict:
                        feature_dict[f'diff_{key}'] = feature_dict[hk] - feature_dict[ak]

                for key in ['momentum_points', 'momentum_goals', 'consistency_score']:
                    hk = f'h_{key}'
                    ak = f'a_{key}'
                    if hk in feature_dict and ak in feature_dict:
                        feature_dict[f'diff_{key}'] = feature_dict[hk] - feature_dict[ak]
            except Exception as e:
                logger.debug(f"Gelişmiş feature hatası: {e}")
                feature_dict['elo_home_win_prob'] = 0.33
                feature_dict['elo_draw_prob'] = 0.33
                feature_dict['elo_away_win_prob'] = 0.33

            # Eksik feature varsa 0.0 doldur
            if features_col is not None:
                for col in features_col:
                    col_str = str(col)
                    if col_str not in feature_dict:
                        feature_dict[col_str] = 0.0

            X_pred = pd.DataFrame([feature_dict])[features_col]
            X_pred_scaled = scaler.transform(X_pred)
            
            # Olasılıkları Çıkar [Beraberlik (0), Ev (1), Deplasman (2)]
            probs = model.predict_proba(X_pred_scaled)[0]
            
            class_mapping = {c: p for c, p in zip(model.classes_, probs)}
            
            # 0: Draw, 1: Home, 2: Away
            draw_prob = class_mapping.get(0, 0.0)
            home_win_prob = class_mapping.get(1, 0.0)
            away_win_prob = class_mapping.get(2, 0.0)

            # ─── Kalibrasyon (cached) ───
            try:
                from calibrator import ModelCalibrator
                if self._calibrator_cache is None:
                    self._calibrator_cache = ModelCalibrator()
                calibrator = self._calibrator_cache
                # Tier'ı geçici olarak belirle (kalibrasyon için)
                raw_confidence = max(home_win_prob, away_win_prob, draw_prob)
                raw_tier = "PLATINUM" if raw_confidence >= 0.65 else ("GOLD" if raw_confidence >= 0.53 else ("SILVER" if raw_confidence >= 0.42 else "BRONZE"))

                # Her olasılığı kalibre et
                home_win_prob = calibrator.calibrate_tier(home_win_prob, raw_tier)
                draw_prob = calibrator.calibrate_tier(draw_prob, raw_tier)
                away_win_prob = calibrator.calibrate_tier(away_win_prob, raw_tier)

                # Normalize et (toplamı 1 olmalı)
                total = home_win_prob + draw_prob + away_win_prob
                if total > 0:
                    home_win_prob /= total
                    draw_prob /= total
                    away_win_prob /= total
            except Exception:
                pass  # Kalibrasyon başarısızsa ham olasılıkları kullan
            
            # ─── 4-Layer Gelişmiş Analiz ───
            
            # Layer 1: Temel Veri (Form, PPG)
            h_ppg = feature_dict['home_points_avg']
            a_ppg = feature_dict['away_points_avg']
            h_form_score = sum(h_stat['points'][:5]) / 5.0 if h_stat['points'] else 1.0
            a_form_score = sum(a_stat['points'][:5]) / 5.0 if a_stat['points'] else 1.0
            
            # Layer 2: İleri Seviye (Synthetic xG & Form Slope)
            def _calc_xg(stats, is_home=True):
                if not stats['scored']: return 1.25 if is_home else 1.1
                
                avg_gs = np.mean(stats['scored'])
                avg_sot = safe_mean(stats.get('shots_on_target', []), default=0)
                avg_s = safe_mean(stats.get('shots', []), default=10)
                
                # Gelişmiş xG: Gol(40%) + SOT(30%) + Shots(10%) + HomeEdge(20%)
                xg_base = (avg_gs * 0.45) + (avg_sot * 0.25) + (avg_s * 0.05)
                if is_home: xg_base += 0.25 # Ev sahibi avantajı
                
                return max(0.5, xg_base)
            
            h_xg = _calc_xg(h_stat, is_home=True)
            a_xg = _calc_xg(a_stat, is_home=False)
            h_xg_diff = h_xg - safe_mean(h_stat['conceded'], default=1.3)
            a_xg_diff = a_xg - safe_mean(a_stat['conceded'], default=1.3)
            
            # Form Trend (Slope)
            h_trend = (h_form_score - h_ppg)
            a_trend = (a_form_score - a_ppg)

            # Layer 3: Bağlamsal (Rest Days - Heuristik)
            # Not: Harici API'den tam tarih farkı almak için scraper'dan veri beslenmeli, şimdilik nötr.
            rest_advantage = 0 
            
            # Layer 4: Pattern (Season Phase)
            total_games = len(h_stat['scored']) + len(a_stat['scored'])
            season_phase = "Early" if total_games < 20 else ("Late" if total_games > 60 else "Mid")

            # Layer 5: Contextual Standings (Phase 14)
            relegation_pressure = False
            must_win = False
            if league_id:
                try:
                    table = self.db.get_league_table(league_id, season_id)
                    if table:
                        sorted_table = sorted(table.values(), key=lambda x: x['points'], reverse=True)
                        teams_list = [t['team'] for t in sorted_table]
                        if home_team in teams_list and away_team in teams_list:
                            h_pos = teams_list.index(home_team) + 1
                            a_pos = teams_list.index(away_team) + 1
                            if h_pos > len(teams_list) - 4 or a_pos > len(teams_list) - 4:
                                relegation_pressure = True
                            if h_pos <= 3 or a_pos <= 3:
                                must_win = True
                except Exception as e:
                    logger.debug(f"Lig tablosu bilgisi alınamadı: {e}")

            # ─── Tier Sınıflandırma (Re-Calibrated for 1X2 Market) ───
            confidence = max(home_win_prob, away_win_prob, draw_prob)
            main_pred = "1" if home_win_prob == confidence else ("2" if away_win_prob == confidence else "X")
            
            # Contextual Adjustments for Draw Bias
            if relegation_pressure and main_pred == "X" and confidence < 0.35:
                # Düşme hattındaki takımlar beraberliğe yatabilir veya tam tersi, ama belirsizlik artar
                confidence -= 0.05 

            # 1X2 marketinde %50 aslında oldukça yüksektir. Thresholdları düşürüyoruz.
            PLATINUM_MIN = 0.65
            GOLD_MIN     = 0.53
            SILVER_MIN   = 0.42

            # Value Detection (Model olasılığı > Bahis şirketi olasılığı)
            odds_prob = 0
            if main_pred == "1" and b365h > 0: odds_prob = 1.0 / b365h
            elif main_pred == "2" and b365a > 0: odds_prob = 1.0 / b365a
            elif main_pred == "X" and b365d > 0: odds_prob = 1.0 / b365d
            
            is_value = (confidence > odds_prob + 0.05) if odds_prob > 0 else False

            # Platinum Şartları: Yüksek confidence + Katman uyumu + (Opsiyonel) Value
            is_platinum = (confidence >= PLATINUM_MIN and 
                           ((main_pred == "1" and h_xg_diff > a_xg_diff + 0.3) or 
                            (main_pred == "2" and a_xg_diff > h_xg_diff + 0.3)))
            
            # Gold Şartları
            is_gold = (confidence >= GOLD_MIN and not is_platinum)
            
            # Silver / Bronze
            is_silver = (confidence >= SILVER_MIN and not is_gold and not is_platinum)
            
            tier = "💎 PLATINUM" if is_platinum else ("🥇 GOLD" if is_gold else ("🥈 SILVER" if is_silver else "🥉 BRONZE"))
            
            # Goals Market (Over 2.5)
            total_goals_exp = h_xg + a_xg
            over_25_prob = min(99.0, max(1.0, (total_goals_exp / 4.0) * 100))

            # Market Switching Recommendation (Phase 14)
            recommended_market = "1X2"
            if confidence < 0.42 and (over_25_prob > 70 or over_25_prob < 30):
                recommended_market = "O/U 2.5"
                tier += " (Alt/Üst Önerilir)"

            advanced_metrics = {
                "layers": {
                    "layer1_base": {"h_ppg": float(round(h_ppg, 2)), "a_ppg": float(round(a_ppg, 2)), "h_form": float(round(h_form_score, 2))},
                    "layer2_adv": {"h_xg": float(round(h_xg, 2)), "a_xg": float(round(a_xg, 2)), "h_trend": float(round(h_trend, 2))},
                    "layer3_context": {"rest_advantage": int(rest_advantage), "season_phase": str(season_phase), "is_value": bool(is_value)},
                    "layer4_standings": {"relegation_pressure": bool(relegation_pressure), "must_win": bool(must_win)}
                },
                "tier_logic": {"confidence": float(round(confidence * 100, 1)), "main_pred": str(main_pred), "odds_prob": float(round(odds_prob*100, 1))}
            }

            return {
                "ml_active": True,
                "teams": {"home": str(home_team), "away": str(away_team)},
                "prediction": str(main_pred),
                "confidence": float(round(confidence * 100, 1)),
                "tier": str(tier),
                "tier_confidence": float(round(confidence * 100, 1)),
                "probabilities": {
                    "home": float(round(home_win_prob * 100, 1)),
                    "draw": float(round(draw_prob * 100, 1)),
                    "away": float(round(away_win_prob * 100, 1))
                },
                "goals_market": {
                    "expected_total_goals": float(round(total_goals_exp, 2)),
                    "over_25": float(round(over_25_prob, 1)),
                    "recommended_market": recommended_market
                },
                "advanced_metrics": advanced_metrics,
                "features_used": {
                    "home_form_edge": float(round(feature_dict.get('home_form_edge', 0.0), 2)),
                    "goal_diff_edge": float(round(feature_dict.get('goal_diff_edge', 0.0), 2)),
                    "home_gd_momentum": float(round(feature_dict.get('home_gd_momentum', 0.0), 2)),
                    "away_gd_momentum": float(round(feature_dict.get('away_gd_momentum', 0.0), 2)),
                    "points_diff": float(round(feature_dict.get('points_diff', 0.0), 2)),
                    "home_yellow_avg": float(round(feature_dict.get('home_yellow_avg', 0.0), 2)),
                    "away_yellow_avg": float(round(feature_dict.get('away_yellow_avg', 0.0), 2))
                }
            }
        except Exception as e:
            logger.error(f"ML Predictor Error: {e}", exc_info=True)
            return {"error": str(e)}

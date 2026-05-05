"""
auto_researcher.py — Otonom Araştırma Döngüsü
================================================
autoresearch/train.py → agent döngüsünün futbol tahmin karşılığı.

Her iterasyonda:
  1. feature_lab'dan yeni bir konfigürasyon alır
  2. İlgili veriyi hazırlar (feature engineering)
  3. Modeli eğitir, cross-validation skoru hesaplar
  4. Sonucu DB'ye kaydeder
  5. Şimdiye kadar en iyi ise "champion" olarak işaretler
  6. Döngü sona erene kadar devam eder

Metrik: weighted F1 (val) — yüksek = daha iyi
"""

import json
import time
import logging
import threading
import numpy as np
import pandas as pd
from datetime import datetime

import os
import shutil
from database import Database
from feature_lab import FeatureLab

logger = logging.getLogger(__name__)

# ─── Durum (thread-safe) ─────────────────────────────────────────

_state = {
    "running": False,
    "current_exp":  0,
    "total_exp":    0,
    "best_score":   None,
    "champion_id":  None,
    "current_desc": "",
    "log":          [],          # Son 50 mesaj
    "started_at":   None,
    "finished_at":  None,
}
_lock = threading.Lock()


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    logger.info(entry)
    with _lock:
        if _state.get("log") is None:
            _state["log"] = []
        _state["log"].append(entry)
        if len(_state["log"]) > 100:
            _state["log"] = _state["log"][-100:]


def get_status() -> dict:
    with _lock:
        return dict(_state)


def stop():
    with _lock:
        _state["running"] = False


# ─── Feature Engineering ─────────────────────────────────────────

def _build_features(df: pd.DataFrame, feature_params: dict, return_dates: bool=False) -> tuple:
    """
    Maç DataFrame'inden ML özellik matrisini oluşturur.
    feature_params (FeatureLab'den gelen) ile kontrol edilir.
    """
    window  = feature_params.get("window_size", 10)
    use_h2h = feature_params.get("use_h2h", True)
    use_odds= feature_params.get("use_odds", True)
    use_fd  = feature_params.get("use_form_diff", True)
    use_gdm = feature_params.get("use_goal_diff_momentum", False)
    use_shots = feature_params.get("use_shots", False)
    use_corners = feature_params.get("use_corners", False)
    weight_recent = feature_params.get("weight_recent", False)

    df = df.copy()
    df["match_date"] = pd.to_datetime(df.get("match_date", df.get("Date", None)), errors="coerce")
    df = df.sort_values("match_date").reset_index(drop=True)

    # Hedef
    df["target"] = df["ftr"].map({"H": 1, "D": 0, "A": 2})
    df = df.dropna(subset=["fthg", "ftag", "ftr", "target"]).copy()
    df["fthg"] = pd.to_numeric(df["fthg"], errors="coerce")
    df["ftag"] = pd.to_numeric(df["ftag"], errors="coerce")

    # Bahis oranları
    for col in ["b365h", "b365d", "b365a"]:
        df[col] = pd.to_numeric(df.get(col, pd.Series([np.nan]*len(df))), errors="coerce")

    team_hist: dict = {}

    def _wma(lst, w):
        """Ağırlıklı hareketli ortalama — sonraki maçlara daha fazla ağırlık."""
        if not lst:
            return 0.0
        arr = np.array(lst[-w:], dtype=float)
        weights = np.arange(1, len(arr)+1, dtype=float)
        return float(np.dot(arr, weights) / weights.sum())

    def _ma(lst, w):
        sub = lst[-w:] if lst else []
        return float(np.mean(sub)) if sub else 0.0

    def _avg(lst: list, window: int) -> float:
        if weight_recent:
            return _wma(lst, window)
        return _ma(lst, window)
    use_gdm      = feature_params.get("use_goal_diff_momentum", False)
    use_shots    = feature_params.get("use_shots", False)
    use_corners  = feature_params.get("use_corners", False)
    use_points   = feature_params.get("use_points", False)
    use_cards    = feature_params.get("use_cards", False)
    m_weight     = feature_params.get("mistake_weight", 1.0)
    
    team_hist: dict = {} # team_name -> {scored: [], conceded: [], ...}
    sample_weights = []

    features, labels, dates_list = [], [], []
    h2h_map: dict = {}   # (home, away) → [(result, date)]

    for _, row in df.iterrows():
        home = row["home_team"]
        away = row["away_team"]
        label = int(row["target"])
        hg, ag = row["fthg"], row["ftag"]

        # H2H
        pair_key = (min(home, away), max(home, away))
        if pair_key not in h2h_map:
            h2h_map[pair_key] = []

        # Feature vektörü yalnızca iki takım hakkında geçmiş varsa
        if home in team_hist and away in team_hist:
            h = team_hist[home]
            a = team_hist[away]

            feat: dict = {
                "home_goals_scored":    _avg(h["scored"], window),
                "home_goals_conceded":  _avg(h["conceded"], window),
                "home_win_rate":        _avg(h["wins"], window),
                "home_draw_rate":       _avg(h["draws"], window),
                "away_goals_scored":    _avg(a["scored"], window),
                "away_goals_conceded":  _avg(a["conceded"], window),
                "away_win_rate":        _avg(a["wins"], window),
                "away_draw_rate":       _avg(a["draws"], window),
            }

            # Form farkı
            if use_fd:
                feat["home_form_edge"] = feat["home_win_rate"] - feat["away_win_rate"]
                feat["goal_diff_edge"] = (
                    (feat["home_goals_scored"] - feat["home_goals_conceded"]) -
                    (feat["away_goals_scored"] - feat["away_goals_conceded"])
                )

            # Gol farkı momentumu
            if use_gdm:
                feat["home_gd_momentum"] = _avg(h["goal_diffs"], window)
                feat["away_gd_momentum"] = _avg(a["goal_diffs"], window)

            # Şut istatistikleri
            if use_shots:
                feat["home_shots_avg"]  = _avg(h.get("shots", []), window)
                feat["away_shots_avg"]  = _avg(a.get("shots", []), window)

                feat["away_corners_avg"]  = _avg(a.get("corners", []), window)

            # Puan Durumu (Standings Proxy)
            if use_points:
                feat["home_points_avg"] = _avg(h.get("points", []), window)
                feat["away_points_avg"] = _avg(a.get("points", []), window)
                feat["points_diff"] = feat["home_points_avg"] - feat["away_points_avg"]

            # Kartlar (Aggression/Suspension Proxy)
            if use_cards:
                feat["home_yellow_avg"] = _avg(h.get("yellow_cards", []), window)
                feat["away_yellow_avg"] = _avg(a.get("yellow_cards", []), window)
                feat["home_red_avg"]    = _avg(h.get("red_cards", []), window)
                feat["away_red_avg"]    = _avg(a.get("red_cards", []), window)

            # H2H
            if use_h2h and h2h_map[pair_key]:
                h2h_list = h2h_map[pair_key][-window:]
                home_h2h_wins = sum(1 for r, _ in h2h_list if r == "H") / len(h2h_list)
                feat["h2h_home_win_rate"] = home_h2h_wins

            # Bahis oranları
            if use_odds:
                feat["b365h"] = row["b365h"] if pd.notna(row["b365h"]) else 2.0
                feat["b365d"] = row["b365d"] if pd.notna(row["b365d"]) else 3.0
                feat["b365a"] = row["b365a"] if pd.notna(row["b365a"]) else 2.5

            features.append(feat)
            labels.append(label)
            dates_list.append(row["match_date"])
            
            # Mistake Weighting
            w = 1.0
            if row.get("prediction_status") == "lost":
                w = m_weight
            sample_weights.append(w)

        # Geçmişi güncelle
        for team, gs, gc, gd, won, drew in [
            (home, hg, ag, hg-ag, row["ftr"]=="H", row["ftr"]=="D"),
            (away, ag, hg, ag-hg, row["ftr"]=="A", row["ftr"]=="D"),
        ]:
            if team not in team_hist:
                team_hist[team] = {
                    "scored": [], "conceded": [], "wins": [],
                    "draws": [], "goal_diffs": [], "shots": [], "corners": [],
                    "points": [], "yellow_cards": [], "red_cards": [],
                }
            h_ptr: dict = team_hist[team]
            if pd.notna(gs): h_ptr["scored"].append(gs)
            if pd.notna(gc): h_ptr["conceded"].append(gc)
            h_ptr["wins"].append(1 if won else 0)
            h_ptr["draws"].append(1 if drew else 0)
            h_ptr["goal_diffs"].append(gd if pd.notna(gd) else 0)

            hs = row.get("home_shots") if team == home else row.get("away_shots")
            if pd.notna(hs) and hs is not None:
                h_ptr["shots"].append(hs)
            hc = row.get("home_corners") if team == home else row.get("away_corners")
            if pd.notna(hc) and hc is not None:
                h_ptr["corners"].append(hc)
            
            # Puanlar
            h_ptr["points"].append(3 if won else (1 if drew else 0))
            
            # Kartlar (Eğer veri varsa)
            yc = row.get("home_yellow") if team == home else row.get("away_yellow")
            if pd.notna(yc): h_ptr["yellow_cards"].append(yc)
            rc = row.get("home_red") if team == home else row.get("away_red")
            if pd.notna(rc): h_ptr["red_cards"].append(rc)

        h2h_map[pair_key].append((row["ftr"], row["match_date"]))

    if not features:
        if return_dates: return pd.DataFrame(), np.array([]), np.array([])
        return pd.DataFrame(), np.array([])

    X = pd.DataFrame(features).fillna(0)
    y = np.array(labels)
    sw = np.array(sample_weights)
    
    if return_dates:
        return X, y, pd.to_datetime(dates_list), sw
    return X, y, sw


# ─── Model İnşası ────────────────────────────────────────────────

def _build_model(model_type: str, model_params: dict):
    """model_type ve params'a göre scikit-learn uyumlu model döndürür."""
    from sklearn.ensemble import RandomForestClassifier, VotingClassifier
    from xgboost import XGBClassifier
    from lightgbm import LGBMClassifier
    
    try:
        from catboost import CatBoostClassifier
        has_cat = True
    except ImportError:
        has_cat = False

    def _xgb(p, prefix=""):
        return XGBClassifier(
            use_label_encoder=False,
            eval_metric="mlogloss",
            n_estimators=p.get(f"{prefix}n_estimators", 100),
            max_depth=p.get(f"{prefix}max_depth", 5),
            learning_rate=p.get(f"{prefix}learning_rate", 0.1),
            subsample=p.get(f"{prefix}subsample", 0.8),
            colsample_bytree=p.get(f"{prefix}colsample_bytree", 0.8),
            min_child_weight=p.get(f"{prefix}min_child_weight", 1),
            random_state=42,
            verbosity=0,
        )

    def _lgbm(p, prefix=""):
        return LGBMClassifier(
            n_estimators=p.get(f"{prefix}n_estimators", 100),
            max_depth=p.get(f"{prefix}max_depth", -1),
            learning_rate=p.get(f"{prefix}learning_rate", 0.1),
            num_leaves=p.get(f"{prefix}num_leaves", 31),
            subsample=p.get(f"{prefix}subsample", 0.8),
            colsample_bytree=p.get(f"{prefix}colsample_bytree", 0.8),
            random_state=42,
            verbose=-1,
        )

    def _rf(p, prefix=""):
        return RandomForestClassifier(
            n_estimators=p.get(f"{prefix}n_estimators", 100),
            max_depth=p.get(f"{prefix}max_depth", None),
            min_samples_split=p.get(f"{prefix}min_samples_split", 2),
            min_samples_leaf=p.get(f"{prefix}min_samples_leaf", 1),
            max_features=p.get(f"{prefix}max_features", "sqrt"),
            random_state=42,
        )

    def _cat(p, prefix=""):
        if not has_cat:
            return _xgb(p, prefix)
        return CatBoostClassifier(
            iterations=p.get(f"{prefix}iterations", 100),
            depth=p.get(f"{prefix}depth", 6),
            learning_rate=p.get(f"{prefix}learning_rate", 0.1),
            l2_leaf_reg=p.get(f"{prefix}l2_leaf_reg", 3),
            random_seed=42,
            verbose=False
        )

    def _lstm(p, prefix=""):
        # LSTM representation constraint: PyTorch deep learning wrapper or scikit fallback 
        # (Standard MLP fallback if torch is unavailable for stability)
        from sklearn.neural_network import MLPClassifier
        return MLPClassifier(
            hidden_layer_sizes=p.get(f"{prefix}hidden_layer_sizes", (64, 32)),
            activation="relu",
            solver="adam",
            alpha=p.get(f"{prefix}alpha", 0.0001),
            max_iter=p.get(f"{prefix}max_iter", 200),
            random_state=42
        )

    p = model_params
    if model_type == "xgboost":
        return _xgb(p)
    elif model_type == "lightgbm":
        return _lgbm(p)
    elif model_type == "catboost":
        return _cat(p)
    elif model_type == "lstm":
        return _lstm(p)
    elif model_type == "random_forest":
        return _rf(p)
    elif model_type == "ensemble_xgb_lgbm":
        return VotingClassifier(
            estimators=[("xgb", _xgb(p, "xgb_")), ("lgbm", _lgbm(p, "lgbm_"))],
            voting=p.get("voting", "soft"),
        )
    elif model_type == "ensemble_full":
        return VotingClassifier(
            estimators=[
                ("xgb", _xgb(p, "xgb_")),
                ("lgbm", _lgbm(p, "lgbm_")),
                ("rf", _rf(p, "rf_")),
            ],
            voting=p.get("voting", "soft"),
        )
    else:
        return _xgb(p)


# ─── Tek Deney & Backtest ────────────────────────────────────────────────

def run_experiment(db: Database, config: dict) -> dict:
    """
    Verilen konfigürasyonla tek bir deney çalıştırır (Optuna için).
    Son 30 günü Test (Backtest), öncesini Train olarak ayırır.
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score
    import datetime

    t0 = time.time()
    model_type   = config["model_type"]
    model_params = config["model_params"]
    feat_params  = config["feature_params"]

    try:
        import os
        limit = 15000 if os.environ.get("RENDER") else 150000
        matches = db.get_matches(limit=limit)
        resolved = db.get_resolved_predictions_for_training()
        df = pd.DataFrame(matches + resolved)

        if df.empty:
            return {"cv_score": 0, "backtest_accuracy": 0, "backtest_profit": 0, "error": "Veri yok", "train_samples": 0}

        X, y, dates, weights = _build_features(df, feat_params, return_dates=True)
        if X.empty or len(y) < 100:
            return {"cv_score": 0, "backtest_accuracy": 0, "backtest_profit": 0, "error": "Yetersiz veri", "train_samples": len(y)}

        cutoff_date = dates.max() - pd.Timedelta(days=30)
        
        train_mask = dates < cutoff_date
        test_mask = dates >= cutoff_date
        
        X_train, y_train, w_train = X[train_mask], y[train_mask], weights[train_mask]
        X_test, y_test            = X[test_mask], y[test_mask]
        
        if len(y_train) < 50 or len(y_test) < 10:
             return {"cv_score": 0, "backtest_accuracy": 0, "backtest_profit": 0, "error": "Test/Train bölme hatası", "train_samples": len(y_train)}

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s  = scaler.transform(X_test)

        model = _build_model(model_type, model_params)
        
        # Fit with sample weights if supported
        try:
            model.fit(X_train_s, y_train, sample_weight=w_train)
        except TypeError:
            # Bazı modeller (örn. MLP) sample_weight desteklemez
            model.fit(X_train_s, y_train)

        # Baseline CV Skorunu Hızlıca Train Set Üzerinde Al (Optuna'ya profit döneceğiz ama loglamak için)
        cv_score = 0.0 # Hız için atlanabilir, direkt test set üzerinden ölçülür
        
        # Test Set Prediction
        y_pred = model.predict(X_test_s)
        acc = accuracy_score(y_test, y_pred)
        
        # Simulated Profit (Mock +1.5/-1 Unit bet on Home/Away/Draw)
        profit = 0.0
        
        test_df = df.iloc[X[test_mask].index].copy() if hasattr(X, "index") else df.tail(len(y_test))
        # Futbol (1-X-2) maçlarında ortalama iddaa oranları 2.50 (Kazanç +1.5 unit) civarındadır.
        for i, (pred_label, true_label) in enumerate(zip(y_pred, y_test)):
            if pred_label == true_label:
                # 3 İhtimalli pazarda ortalama başarı ROI'si (+1.5 unit varsayımı)
                profit += 1.5
            else:
                profit -= 1.0

        return {
            "cv_score": float(round(acc, 4)), 
            "backtest_accuracy": float(round(acc, 4)),
            "backtest_profit": float(round(profit, 2)),
            "error": None,
            "duration_sec": float(round(time.time() - t0, 2)),
            "train_samples": len(y_train),
            "config": config,
        }

    except Exception as e:
        logger.error(f"Deney hatası: {e}", exc_info=True)
        return {
            "cv_score": 0.0, "backtest_accuracy": 0.0, "backtest_profit": 0.0,
            "error": str(e), "duration_sec": float(round(time.time() - t0, 2)), "train_samples": 0, "config": config
        }

# ─── Araştırma Döngüsü ───────────────────────────────────────────

class AutoResearcher:
    """Otonom araştırma motoru (Optuna)."""

    def __init__(self, db: Database, on_promotion_callback=None):
        self.db = db
        self.on_promotion_callback = on_promotion_callback
        self.session_best_id = None
        self.session_best_profit = -9999.0

    def run_research_loop(
        self,
        n_experiments: int = 20,
        time_budget_min: float = 60,
        continuous: bool = False,
        on_progress=None,
    ):
        """Optuna ile Otonom araştırma döngüsünü başlatır."""
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError:
            _log("⏳ Optuna ve CatBoost kütüphaneleri otomatik kuruluyor... (Bu işlem 1-2 dakika sürebilir, lütfen bekleyin)")
            import subprocess, sys
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "optuna", "catboost"])
                import optuna
                optuna.logging.set_verbosity(optuna.logging.WARNING)
                _log("✅ Optuna ve CatBoost başarıyla kuruldu! Deneyler başlıyor...")
            except Exception as e:
                _log(f"❌ Otomatik kurulum başarısız oldu: {e}")
                return
            
        with _lock:
            if _state["running"]: return
            _state["running"] = True
            _state["started_at"] = datetime.now().isoformat()
            
        t_start = time.time()
        budget_sec = time_budget_min * 60

        _log(f"🚀 AutoResearch (Optuna) başlatıldı | {n_experiments} deney limiti")

        # Oturumun en iyisini takip et
        self.session_best_id = None
        self.session_best_profit = -9999.0

        # Oturumun en iyisini takip et
        self.session_best_id = None
        self.session_best_profit = -9999.0

        def objective(trial):
            # 1. Feature Params
            feat_params = {
                "window_size": trial.suggest_categorical("window_size", [5, 7, 10, 15]),
                "use_h2h": trial.suggest_categorical("use_h2h", [True, False]),
                "use_odds": False, # Daha stabil test için
                "use_form_diff": trial.suggest_categorical("use_form_diff", [True, False])
            }
            
            # 2. Model Params
            model_type = trial.suggest_categorical("model_type", ["xgboost", "lightgbm", "catboost", "lstm", "random_forest"])
            model_params = {}
            if model_type in ["xgboost", "lightgbm", "catboost"]:
                model_params["learning_rate"] = trial.suggest_float("lr", 0.01, 0.2, log=True)
                if model_type == "xgboost":
                    model_params["n_estimators"] = trial.suggest_int("n_est", 50, 300)
                    model_params["max_depth"] = trial.suggest_int("max_depth", 3, 8)
                elif model_type == "lightgbm":
                    model_params["n_estimators"] = trial.suggest_int("n_est_l", 50, 300)
                    model_params["num_leaves"] = trial.suggest_int("num_leaves", 15, 63)
                elif model_type == "catboost":
                    model_params["iterations"] = trial.suggest_int("iter_c", 50, 200)
                    model_params["depth"] = trial.suggest_int("depth_c", 4, 8)
            elif model_type == "lstm":
                model_params["max_iter"] = trial.suggest_int("max_iter", 100, 300)
            
            config = {"model_type": model_type, "model_params": model_params, "feature_params": feat_params}
            
            result = run_experiment(self.db, config)
            profit = result.get("backtest_profit", -999.0)
            
            if result.get("error"):
                _log(f"   ❌ Deney Hatası: {result['error']}")
                raise optuna.exceptions.TrialPruned()
            
            # Kaydet 
            exp_id = self.db.save_experiment(result)
            
            acc = result.get("backtest_accuracy", 0)
            _log(f"   ✅ Deney | Model: {model_type} | Acc: {acc:.4f} | Profit: {profit:.1f}U")
            
            # Oturumun en iyisini güncelle
            if profit > self.session_best_profit:
                self.session_best_profit = profit
                self.session_best_id = exp_id
                
            return profit # Optimize objective

        try:
            study = optuna.create_study(direction="maximize")
            study.optimize(objective, n_trials=n_experiments, timeout=budget_sec if not continuous else None)
            
            # OTURUM SONU: Eğer oturumun en iyisi, genel şampiyondan iyiyse PROMOTE ET
            if self.session_best_id:
                history_best = self.db.get_best_historical_experiment()
                global_best_profit = history_best.get("backtest_profit", -9999.0) if history_best else -9999.0
                
                if self.session_best_profit > global_best_profit:
                    _log(f"🏆 OTURUM ŞAMPİYONU! (Profit: {self.session_best_profit:.1f} > Genel: {global_best_profit:.1f}). İşleme alınıyor...")
                    self.db.set_champion_experiment(self.session_best_id)
                    # Arka planda promote et
                    threading.Thread(target=self.promote_champion, args=(self.session_best_id,), daemon=True).start()
                else:
                    _log(f"ℹ️ Oturum bitti. En iyi sonuç ({self.session_best_profit:.1f}) genel rekoru ({global_best_profit:.1f}) kıramadı.")

        except Exception as e:
            _log(f"Optuna Döngü Hatası: {e}")

        with _lock:
            _state["running"] = False
        _log(f"🏁 Araştırma tamamlandı.")

    def start_background(self, n_experiments=20, time_budget_min=60, continuous=False):
        """Araştırmayı arka plan thread'inde başlatır."""
        # Başlarken bir senkronize et (En iyi model aktif olsun)
        self.sync_active_model_with_champion()
        
        t = threading.Thread(
            target=self.run_research_loop,
            kwargs={"n_experiments": n_experiments, "time_budget_min": time_budget_min, "continuous": continuous},
            daemon=True,
        )
        t.start()
        return t

    def promote_champion(self, exp_id: int = None) -> bool:
        """
        En iyi deney konfigürasyonunu canlı sisteme aktarır. 
        Eski modeli model_archive klasörüne yedekler.
        """
        if exp_id:
            # Belirli bir deney id'sini promote et
            self.db.set_champion_experiment(exp_id)
            champion = self.db.get_champion_experiment()
        else:
            # Tüm zamanların en iyisini bul ve promote et
            champion = self.db.get_best_historical_experiment()
            if champion:
                self.db.set_champion_experiment(champion["id"])

        if not champion: return False

        import os, shutil
        # Arşivle
        if os.path.exists("ml_model.pkl"):
            os.makedirs("models_archive", exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy("ml_model.pkl", f"models_archive/ml_model_v{stamp}.pkl")
            _log(f"📦 Eski model arşive kopyalandı: v{stamp}")
            
        config = json.loads(champion["config_json"])
        _log(f"⬆️ Canlı modele promote ediliyor... Profit: {champion.get('backtest_profit')}U")

        try:
            from ml_predictor import MLPredictor
            predictor = MLPredictor(self.db)
            ok = predictor.train_model_with_config(config)
            if ok: 
                _log("✅ Güncel şampiyon aktif edildi!")
                if self.on_promotion_callback:
                    _log("🔔 Promosyon callback tetikleniyor (Tahminler tazelenecek)...")
                    threading.Thread(target=self.on_promotion_callback, daemon=True).start()
            return ok
        except Exception as e:
            _log(f"❌ Promote hatası: {e}")
            return False

    def sync_active_model_with_champion(self):
        """
        Başlangıçta veya periyodik olarak çağrılır. 
        DB'deki şampiyon ile diskteki ml_model.pkl'in uyumlu olduğundan emin olur.
        """
        champion = self.db.get_best_historical_experiment()
        if not champion:
            return
            
        _log("🔍 Şampiyon senkronizasyonu kontrol ediliyor...")
        # Eğer champion_id set edilmemişse set et
        self.db.set_champion_experiment(champion["id"])
        
        # Diskteki model yoksa hemen eğit
        if not os.path.exists("ml_model.pkl"):
            _log("⚠️ Aktif model bulunamadı. Şampiyon konfigürasyonu ile eğitiliyor...")
            self.promote_champion(champion["id"])
        else:
            # Şimdilik sadece varlığını kontrol ediyoruz, 
            # ileride model hash/versiyon kontrolü eklenebilir.
            _log("✅ Aktif model mevcut.")

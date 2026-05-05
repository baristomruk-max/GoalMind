"""
feature_lab.py — AutoResearch Özellik & Hiperparametre Laboratuvarı
====================================================================
Denenecek konfigürasyonları tanımlar ve bir sonraki deneyi önerir.
autoresearch/program.md'nin Python karşılığıdır.
"""

import random
import numpy as np

# ─── DENEY UZAYI ─────────────────────────────────────────────────

# Model tipleri ve hiperparametreleri
MODEL_CONFIGS = {
    "xgboost": {
        "n_estimators":   [50, 100, 200, 300],
        "max_depth":      [3, 4, 5, 6, 8],
        "learning_rate":  [0.01, 0.05, 0.1, 0.2],
        "subsample":      [0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.7, 0.8, 1.0],
        "min_child_weight": [1, 3, 5],
    },
    "lightgbm": {
        "n_estimators":   [50, 100, 200, 300],
        "max_depth":      [3, 5, 7, -1],
        "learning_rate":  [0.01, 0.05, 0.1, 0.2],
        "num_leaves":     [15, 31, 63, 127],
        "subsample":      [0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.7, 0.8, 1.0],
    },
    "random_forest": {
        "n_estimators":   [50, 100, 200, 300],
        "max_depth":      [None, 5, 10, 15],
        "min_samples_split": [2, 5, 10],
        "min_samples_leaf":  [1, 2, 4],
        "max_features":   ["sqrt", "log2"],
    },
    "ensemble_xgb_lgbm": {
        # Sadece ikisinin birleşimi
        "xgb_n_estimators":  [100, 200],
        "xgb_max_depth":     [4, 5, 6],
        "lgbm_n_estimators": [100, 200],
        "lgbm_num_leaves":   [31, 63],
        "voting":            ["soft"],
    },
    "ensemble_full": {
        # Üçlü: XGB + LGBM + RF
        "xgb_n_estimators":  [100, 200],
        "lgbm_n_estimators": [100, 200],
        "rf_n_estimators":   [100, 200],
        "voting":            ["soft"],
    },
}

# Özellik mühendisliği seçenekleri
FEATURE_CONFIGS = {
    "window_size":       [5, 7, 10, 15, 20],     # Son N maç penceresi
    "use_h2h":          [True, False],             # Head-to-Head istatistikleri
    "use_odds":         [True, False],             # Bahis oranları
    "use_form_diff":    [True, False],             # Ev/Deplasman form farkı
    "use_goal_diff_momentum": [True, False],       # Gol farkı momentumu
    "use_shots":        [True, False],             # Şut istatistikleri
    "use_corners":      [True, False],             # Korner istatistikleri
    "use_half_time":    [True, False],             # İlk yarı sonuçları
    "weight_recent":    [True, False],             # Son maçlara daha fazla ağırlık
    "mistake_weight":   [1.0, 1.5, 2.0, 3.0],      # Yanlış tahminlere verilen ekstra ağırlık
    "use_points":       [True, False],             # Puan durumu (ortalama) özelliği
    "use_cards":        [True, False],             # Kart (sarı/kırmızı) ortalamaları
}


class FeatureLab:
    """
    Araştırma döngüsü için bir sonraki deneyi önerir.
    autoresearch'teki 'agent' rolünü üstlenir — ancak ML tabanlı.
    
    Strateji:
      1. İlk N deney → tamamen rastgele (keşif / exploration)
      2. Sonraki deneyler → şimdiye kadar en iyi bulunan 
         konfigürasyonun yakınında pertürbasyon (sömürü / exploitation)
    """

    def __init__(self, exploration_ratio: float = 0.4):
        self.exploration_ratio = exploration_ratio  # İlk %40 tamamen rastgele

    def suggest(self, experiment_history: list) -> dict:
        """
        Bir sonraki deneyin konfigürasyonunu önerir.
        
        Args:
            experiment_history: Geçmiş deneylerin listesi (her biri dict)
        
        Returns:
            config dict: model_type, model_params, feature_params
        """
        n = len(experiment_history)

        # Keşif fazı: tamamen rastgele
        if n == 0 or (n < 5) or (random.random() < self.exploration_ratio):
            return self._random_config()

        # Sömürü fazı: en iyi konfigürasyonu baz alıp pertürbe et
        best = self._get_best(experiment_history)
        if best:
            return self._perturb_config(best["config"])

        return self._random_config()

    def _random_config(self) -> dict:
        """Tamamen rastgele bir konfigürasyon üretir."""
        model_type = random.choice(list(MODEL_CONFIGS.keys()))
        model_params = {
            k: random.choice(v)
            for k, v in MODEL_CONFIGS[model_type].items()
        }
        feature_params = {
            k: random.choice(v)
            for k, v in FEATURE_CONFIGS.items()
        }
        return {
            "model_type": model_type,
            "model_params": model_params,
            "feature_params": feature_params,
        }

    def _get_best(self, history: list) -> dict | None:
        """Geçmiş deneylerin en yüksek skorlusu."""
        resolved = [h for h in history if h.get("cv_score") is not None]
        if not resolved:
            return None
        best = max(resolved, key=lambda h: h["cv_score"])
        # DB'den gelen kayıtlarda "config_json" (string) var, "config" (dict) yok.
        # _perturb_config için config dict'e çevir.
        if "config" not in best and "config_json" in best:
            import json
            best = dict(best)
            try:
                best["config"] = json.loads(best["config_json"])
            except Exception:
                best["config"] = {}
        return best


    def _perturb_config(self, base_config: dict) -> dict:
        """
        Mevcut en iyi konfigürasyonu küçük çaplı değişikliklerle
        pertürbe eder (lokale keşif / hillclimbing).
        """
        import copy
        config = copy.deepcopy(base_config)
        model_type = config["model_type"]

        # Model parametrelerinden 1-2 tanesini rastgele değiştir
        if model_type in MODEL_CONFIGS:
            keys = list(MODEL_CONFIGS[model_type].keys())
            n_changes = random.randint(1, min(2, len(keys)))
            for k in random.sample(keys, n_changes):
                config["model_params"][k] = random.choice(MODEL_CONFIGS[model_type][k])

        # Feature parametrelerinden 1-2 tanesini değiştir
        feat_keys = list(FEATURE_CONFIGS.keys())
        n_fchanges = random.randint(1, min(2, len(feat_keys)))
        for k in random.sample(feat_keys, n_fchanges):
            config["feature_params"][k] = random.choice(FEATURE_CONFIGS[k])

        return config

    def describe(self, config: dict) -> str:
        """İnsan okunabilir konfigürasyon özeti."""
        mt = config.get("model_type", "?")
        fp = config.get("feature_params", {})
        mp = config.get("model_params", {})
        return (
            f"Model={mt} | "
            f"Window={fp.get('window_size', '?')} | "
            f"H2H={fp.get('use_h2h', '?')} | "
            f"Odds={fp.get('use_odds', '?')} | "
            f"FormDiff={fp.get('use_form_diff', '?')} | "
            f"Params={str(mp)[:60]}..."
        )

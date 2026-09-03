"""
Self-Learning Motoru
Tahmin hatalarından öğrenen, ağırlıkları adapte eden, otomatik yeniden eğitim tetikleyen sistem.

Döngü:
1. Tahmin yap → Sonuçlanma bekle
2. Hataları analiz et (Neden yanlış?)
3. Ağırlıkları güncelle (Hangi feature daha önemli?)
4. Gerekirse yeniden eğit (Yeterli hata biriktiyse)
5. Kalibrasyonu güncelle

Referanslar:
- Online Learning: Shalev-Shwartz et al. (2011)
- Feature Importance: Lundberg & Lee (2017) SHAP
- Adaptive Weights: Freund & Schapire (1997) AdaBoost
"""
import os
import json
import logging
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class SelfLearningEngine:
    """
    Self-learning motoru.
    Hata analizi, adaptif ağırlık ve otomatik yeniden eğitimi yönetir.
    """

    def __init__(self, db=None):
        self.db = db
        self.state_file = os.path.join("data", "self_learning_state.json")
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Durum dosyasını yükler."""
        default = {
            "mistakes": [],           # Hata kayıtları
            "feature_weights": {},    # Adaptif ağırlıklar
            "retrain_trigger": 0,     # Yeniden eğitim tetikleyici
            "last_analysis": None,    # Son analiz tarihi
            "total_predictions": 0,
            "total_correct": 0,
            "accuracy_trend": [],     # Accuracy geçmişi
            "weight_history": [],     # Ağırlık değişim geçmişi
            "league_performance": {}, # Lig bazlı performans
            "feature_performance": {},# Feature bazlı performans
        }

        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                default.update(saved)
            except Exception as e:
                logger.error(f"Self-learning state yükleme hatası: {e}")

        return default

    def _save_state(self):
        """Durum dosyasını kaydeder."""
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Self-learning state kaydetme hatası: {e}")

    # ─── Hata Analizi Motoru ───

    def analyze_mistake(self, prediction: dict, actual_result: dict, features: dict = None) -> dict:
        """
        Bir tahmin hatasını analiz eder.

        Args:
            prediction: Tahmin verisi {prediction, confidence, tier, probabilities, teams, ...}
            actual_result: Gerçek sonuç {home_goals, away_goals, ftr}
            features: Kullanılan feature'lar (opsiyonel)

        Returns:
            Hata analiz sonucu
        """
        pred = prediction.get("prediction", "")
        conf = prediction.get("confidence", 50) / 100.0
        tier = prediction.get("tier", "BRONZE")
        teams = prediction.get("teams", {})
        home = teams.get("home", "")
        away = teams.get("away", "")

        ftr = actual_result.get("ftr", "")
        hg = actual_result.get("home_goals", 0)
        ag = actual_result.get("away_goals", 0)

        # Gerçek sonuç
        if ftr == "H":
            actual = "1"
        elif ftr == "D":
            actual = "X"
        else:
            actual = "2"

        is_correct = pred == actual

        # Hata türünü belirle
        mistake_type = "none"
        mistake_detail = ""
        if not is_correct:
            if pred == "1" and actual == "X":
                mistake_type = "draw_missed"
                mistake_detail = "Ev sahibi galibiyet bekleniyor ama beraberlik"
            elif pred == "1" and actual == "2":
                mistake_type = "upset_loss"
                mistake_detail = "Ev sahibi galibiyet bekleniyor ama deplasman kazanıyor"
            elif pred == "X" and actual == "1":
                mistake_type = "draw_to_win"
                mistake_detail = "Beraberlik bekleniyor ama ev sahibi kazanıyor"
            elif pred == "X" and actual == "2":
                mistake_type = "draw_to_away"
                mistake_detail = "Beraberlik bekleniyor ama deplasman kazanıyor"
            elif pred == "2" and actual == "1":
                mistake_type = "upset_home"
                mistake_detail = "Deplasman galibiyet bekleniyor ama ev sahibi kazanıyor"
            elif pred == "2" and actual == "X":
                mistake_type = "draw_missed_away"
                mistake_detail = "Deplasman galibiyet bekleniyor ama beraberlik"
            elif pred == "1" and actual == "2":
                mistake_type = "wrong_winner"
                mistake_detail = "Tam tersi sonuç"

        # Hata güven skoru (ne kadar yanlış?)
        error_confidence = conf if not is_correct else 0

        # Gol farkı analizi
        goal_diff = hg - ag

        record = {
            "timestamp": datetime.now().isoformat(),
            "home": home,
            "away": away,
            "prediction": pred,
            "actual": actual,
            "confidence": conf,
            "tier": tier,
            "is_correct": is_correct,
            "mistake_type": mistake_type,
            "mistake_detail": mistake_detail,
            "error_confidence": error_confidence,
            "home_goals": hg,
            "away_goals": ag,
            "goal_diff": goal_diff,
        }

        # Feature analizi (hangi feature yanılttı?)
        if features and not is_correct:
            record["feature_analysis"] = self._analyze_feature_mistake(features, pred, actual)

        # Hata kaydını ekle
        self.state["mistakes"].append(record)

        # Son 500 hatayı tut
        if len(self.state["mistakes"]) > 500:
            self.state["mistakes"] = self.state["mistakes"][-500:]

        # İstatistikleri güncelle
        self.state["total_predictions"] += 1
        if is_correct:
            self.state["total_correct"] += 1

        # Yeniden eğitim tetikleyicisi
        if not is_correct and conf > 0.6:
            self.state["retrain_trigger"] += 1

        self._save_state()

        return record

    def _analyze_feature_mistake(self, features: dict, pred: str, actual: str) -> dict:
        """Hangi feature'ların yanıltıcı olduğunu analiz eder."""
        analysis = {}

        # Ev/deplasman form karşılaştırması
        h_ppg = features.get("home_points_avg", 1.5)
        a_ppg = features.get("away_points_avg", 1.5)

        if pred == "1" and actual != "1":
            if h_ppg <= a_ppg:
                analysis["form_mismatch"] = "Ev sahibi formu düşük ama galibiyet bekleniyor"
            if features.get("home_goals_conceded", 1.2) > 1.5:
                analysis["defensive_weakness"] = "Ev sahibi çok gol yiyor"

        elif pred == "2" and actual != "2":
            if a_ppg <= h_ppg:
                analysis["form_mismatch"] = "Deplasman formu düşük ama galibiyet bekleniyor"

        elif pred == "X" and actual != "X":
            h_form = features.get("home_win_rate", 0.33)
            a_form = features.get("away_win_rate", 0.33)
            if h_form > 0.5 or a_form > 0.5:
                analysis["form_mismatch"] = "Takımlardan biri çok formda, beraberlik beklenmemeli"

        return analysis

    # ─── Adaptif Ağırlık Sistemi ───

    def update_feature_weights(self, features_used: dict, is_correct: bool, confidence: float):
        """
        Feature ağırlıklarını güncelle.
        Doğru tahminlerde ağırlık artar, yanlış tahminlerde azalır.

        Args:
            features_used: Kullanılan feature'lar {feature_name: value}
            is_correct: Tahmin doğru muydu?
            confidence: Tahmin güven skoru (0-1)
        """
        if not self.state["feature_weights"]:
            # İlk kez - tüm ağırlıkları 1.0 yap
            for fname in features_used:
                self.state["feature_weights"][fname] = 1.0

        # Doğruluk oranına göre ağırlık güncelleme hızı
        learning_rate = 0.05

        for fname, fval in features_used.items():
            if fname not in self.state["feature_weights"]:
                self.state["feature_weights"][fname] = 1.0

            current_weight = self.state["feature_weights"][fname]

            if is_correct:
                # Doğru tahmin - bu feature'a güven artar
                boost = learning_rate * confidence
                self.state["feature_weights"][fname] = min(2.0, current_weight + boost)
            else:
                # Yanlış tahmin - bu feature'a güven azalır
                penalty = learning_rate * confidence
                self.state["feature_weights"][fname] = max(0.1, current_weight - penalty)

        self._save_state()

    def get_weighted_features(self, features: dict) -> dict:
        """Ağırlıklı feature'ları döner."""
        if not self.state["feature_weights"]:
            return features

        weighted = {}
        for fname, fval in features.items():
            weight = self.state["feature_weights"].get(fname, 1.0)
            weighted[fname] = fval * weight

        return weighted

    # ─── Lig Bazlı Performans ───

    def update_league_performance(self, league: str, is_correct: bool, confidence: float):
        """Lig bazlı performans kaydı tutar."""
        if league not in self.state["league_performance"]:
            self.state["league_performance"][league] = {
                "total": 0, "correct": 0, "avg_confidence": 0,
                "accuracy_history": []
            }

        perf = self.state["league_performance"][league]
        perf["total"] += 1
        if is_correct:
            perf["correct"] += 1
        perf["avg_confidence"] = (perf["avg_confidence"] * (perf["total"] - 1) + confidence) / perf["total"]

        # Son 20 tahminin accuracy trend'i
        perf["accuracy_history"].append(1 if is_correct else 0)
        if len(perf["accuracy_history"]) > 20:
            perf["accuracy_history"] = perf["accuracy_history"][-20:]

        self._save_state()

    def get_league_performance(self, league: str = None) -> dict:
        """Lig bazlı performansı döner."""
        if league:
            return self.state["league_performance"].get(league, {})
        return self.state["league_performance"]

    # ─── Accuracy Trend ───

    def update_accuracy_trend(self):
        """Genel accuracy trend'ini günceller."""
        total = self.state["total_predictions"]
        correct = self.state["total_correct"]
        if total > 0:
            accuracy = correct / total
            self.state["accuracy_trend"].append({
                "date": datetime.now().isoformat(),
                "accuracy": round(accuracy, 4),
                "total": total,
                "correct": correct,
            })
            # Son 100 kaydı tut
            if len(self.state["accuracy_trend"]) > 100:
                self.state["accuracy_trend"] = self.state["accuracy_trend"][-100:]
            self._save_state()

    def get_accuracy_trend(self) -> list:
        """Accuracy trend'ini döner."""
        return self.state["accuracy_trend"]

    # ─── Otomatik Yeniden Eğitim Tetikleyicisi ───

    def should_retrain(self, threshold: int = 20) -> bool:
        """
        Yeniden eğitim gerekli mi diye bakar.
        Her 20 yüksek güvenli hata sonrası yeniden eğitim önerilir.

        Args:
            threshold: Hata eşiği
        Returns:
            True = yeniden eğitim gerekli
        """
        return self.state["retrain_trigger"] >= threshold

    def reset_retrain_trigger(self):
        """Yeniden eğitim tetikleyicisini sıfırlar."""
        self.state["retrain_trigger"] = 0
        self._save_state()

    # ─── Hata Raporu ───

    def generate_error_report(self) -> dict:
        """
        Kapsamlı hata raporu oluşturur.

        Returns:
            Hata raporu
        """
        mistakes = self.state["mistakes"]
        if not mistakes:
            return {"message": "Henüz hata kaydı yok", "total_mistakes": 0}

        total = len(mistakes)
        correct = sum(1 for m in mistakes if m["is_correct"])
        wrong = total - correct

        # Hata türü dağılımı
        mistake_types = defaultdict(int)
        for m in mistakes:
            if not m["is_correct"]:
                mistake_types[m["mistake_type"]] += 1

        # Güven dağılımı
        high_conf_mistakes = [m for m in mistakes if not m["is_correct"] and m["confidence"] > 0.6]
        medium_conf_mistakes = [m for m in mistakes if not m["is_correct"] and 0.4 <= m["confidence"] <= 0.6]
        low_conf_mistakes = [m for m in mistakes if not m["is_correct"] and m["confidence"] < 0.4]

        # Lig bazlı hata
        league_mistakes = defaultdict(int)
        for m in mistakes:
            if not m["is_correct"]:
                league_mistakes[f"{m.get('home', '?')} vs {m.get('away', '?')}"] += 1

        # En çok hata yapılan tahminler
        prediction_mistakes = defaultdict(int)
        for m in mistakes:
            if not m["is_correct"]:
                prediction_mistakes[m["prediction"]] += 1

        # Ortalama hata güven skoru
        avg_error_conf = np.mean([m["error_confidence"] for m in mistakes if not m["is_correct"]]) if wrong > 0 else 0

        return {
            "total_analyzed": total,
            "correct": correct,
            "wrong": wrong,
            "accuracy": round(correct / total, 4) if total > 0 else 0,
            "mistake_types": dict(mistake_types),
            "high_confidence_mistakes": len(high_conf_mistakes),
            "medium_confidence_mistakes": len(medium_conf_mistakes),
            "low_confidence_mistakes": len(low_conf_mistakes),
            "avg_error_confidence": round(float(avg_error_conf), 4),
            "prediction_mistakes": dict(prediction_mistakes),
            "top_mistake_matches": sorted(
                [m for m in mistakes if not m["is_correct"]],
                key=lambda x: x["error_confidence"],
                reverse=True
            )[:10],
            "retrain_recommended": self.should_retrain(),
            "retrain_trigger": self.state["retrain_trigger"],
        }

    # ─── Öğrenme Özeti ───

    def get_learning_summary(self) -> dict:
        """Öğrenme durumu özetini döner."""
        total = self.state["total_predictions"]
        correct = self.state["total_correct"]

        return {
            "total_predictions": total,
            "total_correct": correct,
            "accuracy": round(correct / total, 4) if total > 0 else 0,
            "total_mistakes": len(self.state["mistakes"]),
            "feature_weights_count": len(self.state["feature_weights"]),
            "top_features": sorted(
                self.state["feature_weights"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "bottom_features": sorted(
                self.state["feature_weights"].items(),
                key=lambda x: x[1]
            )[:10],
            "retrain_trigger": self.state["retrain_trigger"],
            "retrain_threshold": 20,
            "leagues_tracked": len(self.state["league_performance"]),
        }

    # ─── Temizlik ───

    def clear_old_mistakes(self, days: int = 30):
        """Eski hata kayıtlarını temizler."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        self.state["mistakes"] = [
            m for m in self.state["mistakes"]
            if m.get("timestamp", "") > cutoff
        ]
        self._save_state()

    def reset(self):
        """Tüm learning durumunu sıfırlar."""
        self.state = {
            "mistakes": [],
            "feature_weights": {},
            "retrain_trigger": 0,
            "last_analysis": None,
            "total_predictions": 0,
            "total_correct": 0,
            "accuracy_trend": [],
            "weight_history": [],
            "league_performance": {},
            "feature_performance": {},
        }
        self._save_state()

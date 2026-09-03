"""
Tahmin Kalibrasyon Motoru
Model çıktılarını kalibre ederek tahminlerin güvenilirliğini artırır.

Temel prensip: %60 dediğinde gerçekten %60 kazanmalısın.
Kalibrasyon olmadan accuracy yüksek olsa bile para kaybettirir.

Referanslar:
- Platt Scaling: Platt, J. (1999). "Probabilistic Outputs for Support Vector Machines"
- Isotonic Regression: Zadrozny, B. & Elkan, C. (2001). "Obtaining Calibrated Probability Estimates"
- Guo et al. (2017). "On Calibration of Modern Neural Networks"

Metrikler:
- Brier Score: 0.25 = rastgele, <0.21 = iyi, <0.18 = profesyonel
- ECE: <0.05 = çok iyi kalibre, <0.03 = mükemmel
"""
import os
import json
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import cross_val_predict
    SKLEARN_CALIBRATION_AVAILABLE = True
except ImportError:
    SKLEARN_CALIBRATION_AVAILABLE = False


class ModelCalibrator:
    """
    Model kalibrasyon motoru.
    Farklı kalibrasyon yöntemleri sunar:
    1. Isotonic Regression (esnek, non-parametrik)
    2. Platt Scaling (parametrik, sigmoid)
    3. Temperature Scaling (deep learning için)
    4. Per-tier kalibrasyon
    """

    def __init__(self):
        self.calibrators = {}       # {tier: calibrator}
        self.calibration_data = {}  # {tier: {"preds": [], "outs": []}}
        self.calibration_file = os.path.join("data", "calibration_state.json")
        self._load_state()

    def _load_state(self):
        """Kalibrasyon durumunu yükler."""
        if os.path.exists(self.calibration_file):
            try:
                with open(self.calibration_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.calibration_data = state.get("data", {})
                logger.info(f"Kalibrasyon durumu yüklendi: {len(self.calibration_data)} tier")
            except Exception as e:
                logger.error(f"Kalibrasyon yükleme hatası: {e}")

    def _save_state(self):
        """Kalibrasyon durumunu kaydeder."""
        try:
            os.makedirs(os.path.dirname(self.calibration_file), exist_ok=True)
            with open(self.calibration_file, "w", encoding="utf-8") as f:
                json.dump({"data": self.calibration_data, "updated": datetime.now().isoformat()}, f)
        except Exception as e:
            logger.error(f"Kalibrasyon kaydetme hatası: {e}")

    # ─── Isotonic Regression ───

    def fit_isotonic(self, predictions, outcomes, tier=None):
        """
        Isotonic Regression kalibrasyonu eğitir.
        En esnek yöntem - monotonik olmayan kalibrasyon hatalarını da düzeltir.

        Args:
            predictions: Tahmin olasılıkları (0-1)
            outcomes: Gerçek sonuçlar (0 veya 1)
            tier: Tier adı (opsiyonel, None ise genel kalibratör)
        Returns:
            IsotonicRegression nesnesi
        """
        if not SKLEARN_CALIBRATION_AVAILABLE:
            logger.warning("sklearn kurulu değil, isotonic kalibrasyon yapılamaz.")
            return None

        pred = np.array(predictions, dtype=float)
        out = np.array(outcomes, dtype=float)

        if len(pred) < 10:
            logger.warning("Kalibrasyon için yeterli veri yok (min 10 gerekli).")
            return None

        calibrator = IsotonicRegression(y_min=0.001, y_max=0.999, out_of_bounds="clip")
        calibrator.fit(pred, out)

        key = tier or "global"
        self.calibrators[key] = calibrator

        logger.info(f"Isotonic kalibrasyon eğitildi: {key} ({len(pred)} örnek)")
        return calibrator

    def calibrate_isotonic(self, raw_probs, tier=None):
        """
        Isotonic kalibrasyonu uygular.

        Args:
            raw_probs: Ham tahmin olasılıkları
            tier: Tier adı
        Returns:
            Kalibre edilmiş olasılıklar
        """
        key = tier or "global"
        calibrator = self.calibrators.get(key)

        if calibrator is None:
            # Global kalibratör varsa onu kullan
            calibrator = self.calibrators.get("global")
        if calibrator is None:
            logger.debug("Kalibratör bulunamadı, ham olasılıklar döndürülüyor.")
            return raw_probs

        raw = np.array(raw_probs, dtype=float).reshape(-1, 1)
        calibrated = calibrator.predict(raw.flatten())
        return calibrated.tolist()

    # ─── Platt Scaling ───

    def fit_platt(self, predictions, outcomes, tier=None):
        """
        Platt Scaling (Logistic Regression) kalibrasyonu.
        Sigmoid formunda kalibrasyon - monotonic düzeltmeler için.

        Args:
            predictions: Tahmin olasılıkları
            outcomes: Gerçek sonuçlar
            tier: Tier adı
        Returns:
            LogisticRegression nesnesi
        """
        if not SKLEARN_CALIBRATION_AVAILABLE:
            logger.warning("sklearn kurulu değil, Platt kalibrasyon yapılamaz.")
            return None

        pred = np.array(predictions, dtype=float).reshape(-1, 1)
        out = np.array(outcomes, dtype=float)

        if len(pred) < 10:
            return None

        calibrator = LogisticRegression(C=1e10, solver="lbfgs")
        calibrator.fit(pred, out)

        key = f"platt_{tier}" if tier else "platt_global"
        self.calibrators[key] = calibrator

        logger.info(f"Platt kalibrasyon eğitildi: {key} ({len(pred)} örnek)")
        return calibrator

    def calibrate_platt(self, raw_probs, tier=None):
        """
        Platt kalibrasyonu uygular.

        Args:
            raw_probs: Ham tahmin olasılıkları
            tier: Tier adı
        Returns:
            Kalibre edilmiş olasılıklar
        """
        key = f"platt_{tier}" if tier else "platt_global"
        calibrator = self.calibrators.get(key)
        if calibrator is None:
            calibrator = self.calibrators.get("platt_global")
        if calibrator is None:
            return raw_probs

        raw = np.array(raw_probs, dtype=float).reshape(-1, 1)
        calibrated = calibrator.predict_proba(raw)[:, 1]
        return calibrated.tolist()

    # ─── Per-Tier Kalibrasyon ───

    def collect_prediction(self, prediction, outcome, tier):
        """
        Tahmin ve sonucu tier bazlı toplar.
        Yeterli veri biriktiğinde otomatik kalibrasyon eğitir.

        Args:
            prediction: Tahmin olasılığı (0-1)
            outcome: Gerçek sonuç (0 veya 1)
            tier: Tier adı (PLATINUM/GOLD/SILVER/BRONZE)
        """
        if tier not in self.calibration_data:
            self.calibration_data[tier] = {"preds": [], "outs": [], "count": 0}

        self.calibration_data[tier]["preds"].append(float(prediction))
        self.calibration_data[tier]["outs"].append(float(outcome))
        self.calibration_data[tier]["count"] += 1

        # Son 500 tahmini tut (eski verileri at)
        if len(self.calibration_data[tier]["preds"]) > 500:
            self.calibration_data[tier]["preds"] = self.calibration_data[tier]["preds"][-500:]
            self.calibration_data[tier]["outs"] = self.calibration_data[tier]["outs"][-500:]

        # Her 20 tahminde bir kalibrasyonu güncelle
        if self.calibration_data[tier]["count"] % 20 == 0:
            self._auto_recalibrate(tier)

        self._save_state()

    def _auto_recalibrate(self, tier):
        """Belirli bir tier için otomatik kalibrasyon eğitir."""
        data = self.calibration_data.get(tier, {})
        preds = data.get("preds", [])
        outs = data.get("outs", [])

        if len(preds) < 15:
            return

        self.fit_isotonic(preds, outs, tier=tier)
        self.fit_platt(preds, outs, tier=tier)
        logger.info(f"Tier {tier} kalibrasyonu güncellendi ({len(preds)} örnek)")

    def calibrate_tier(self, raw_prob, tier):
        """
        Belirli bir tier için kalibrasyon uygular.
        Öncelik sırası: Isotonic > Platt > Ham

        Args:
            raw_prob: Ham tahmin olasılığı
            tier: Tier adı
        Returns:
            Kalibre edilmiş olasılık
        """
        # Isotonic dene
        if tier in self.calibrators:
            try:
                calibrated = self.calibrate_isotonic([raw_prob], tier=tier)
                return calibrated[0]
            except Exception:
                pass

        # Platt dene
        platt_key = f"platt_{tier}"
        if platt_key in self.calibrators:
            try:
                calibrated = self.calibrate_platt([raw_prob], tier=tier)
                return calibrated[0]
            except Exception:
                pass

        # Hiçbiri yoksa ham döndür
        return raw_prob

    # ─── Genel Kalibrasyon Analizi ───

    def analyze_calibration(self, predictions, outcomes, n_bins=10):
        """
        Kalibrasyon analizi yapar.
        Her bin için tahmin ortalaması ve gerçek frekansı hesaplar.

        Returns:
            dict: Kalibrasyon analiz sonuçları
        """
        from metrics import brier_score, expected_calibration_error, maximum_calibration_error

        pred = np.array(predictions, dtype=float)
        out = np.array(outcomes, dtype=float)

        if len(pred) == 0:
            return {"error": "Veri yok"}

        # Temel metrikler
        brier = brier_score(pred, out)
        ece = expected_calibration_error(pred, out)
        mce = maximum_calibration_error(pred, out)

        # Kalibrasyon binleri
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bins = []

        for i in range(n_bins):
            lower, upper = bin_boundaries[i], bin_boundaries[i + 1]
            mask = (pred > lower) & (pred <= upper)
            if i == 0:
                mask = (pred >= lower) & (pred <= upper)

            bin_size = int(np.sum(mask))
            if bin_size == 0:
                continue

            bin_pred_mean = float(np.mean(pred[mask]))
            bin_outcome_mean = float(np.mean(out[mask]))
            gap = abs(bin_pred_mean - bin_outcome_mean)

            bins.append({
                "range": f"{lower:.1f}-{upper:.1f}",
                "predicted": round(bin_pred_mean, 4),
                "observed": round(bin_outcome_mean, 4),
                "count": bin_size,
                "gap": round(gap, 4),
                "calibrated": gap < 0.05,  # %5'ten az fark = iyi kalibre
            })

        # Bias analizi
        avg_predicted = float(np.mean(pred))
        avg_observed = float(np.mean(out))
        bias = avg_predicted - avg_observed

        return {
            "brier_score": round(brier, 4),
            "ece": round(ece, 4),
            "mce": round(mce, 4),
            "bias": round(bias, 4),
            "avg_predicted": round(avg_predicted, 4),
            "avg_observed": round(avg_observed, 4),
            "bins": bins,
            "calibration_quality": (
                "Mükemmel" if ece < 0.02 else
                "Çok İyi" if ece < 0.05 else
                "İyi" if ece < 0.10 else
                "Orta" if ece < 0.15 else
                "Kötü"
            ),
            "sample_count": len(pred),
        }

    def get_calibration_offsets(self, predictions, outcomes, n_bins=10):
        """
        Kalibrasyon düzeltmeleri hesaplar.
        Her olasılık bandı için düzeltme miktarını döner.

        Returns:
            dict: {bin_range: offset} - pozitif = yukarı çek, negatif = aşağı çek
        """
        pred = np.array(predictions, dtype=float)
        out = np.array(outcomes, dtype=float)

        if len(pred) < 20:
            return {}

        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        offsets = {}

        for i in range(n_bins):
            lower, upper = bin_boundaries[i], bin_boundaries[i + 1]
            mask = (pred > lower) & (pred <= upper)
            if i == 0:
                mask = (pred >= lower) & (pred <= upper)

            bin_size = int(np.sum(mask))
            if bin_size < 5:  # Minimum 5 örnek
                continue

            gap = float(np.mean(out[mask]) - np.mean(pred[mask]))
            offsets[f"{lower:.1f}-{upper:.1f}"] = round(gap, 4)

        return offsets

    # ─── Veri Dışa Aktarma ───

    def export_calibration_report(self, predictions, outcomes):
        """Kalibrasyon raporu oluşturur."""
        analysis = self.analyze_calibration(predictions, outcomes)
        offsets = self.get_calibration_offsets(predictions, outcomes)

        report = {
            "generated_at": datetime.now().isoformat(),
            "analysis": analysis,
            "offsets": offsets,
            "tier_data": {},
        }

        # Tier bazlı veri
        for tier, data in self.calibration_data.items():
            if len(data["preds"]) > 0:
                tier_analysis = self.analyze_calibration(data["preds"], data["outs"])
                report["tier_data"][tier] = tier_analysis

        return report

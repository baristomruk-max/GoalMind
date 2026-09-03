"""
Tahmin Değerlendirme Metrikleri
Brier Score, ECE, RPS, Log Loss ve diğer kalibrasyon metrikleri.

Referanslar:
- Brier Score: Brier, G.W. (1950). "Verification of Forecasts Expressed in Terms of Probability"
- ECE: Guo et al. (2017). "On Calibration of Modern Neural Networks"
- RPS: Ranked Probability Score (epik kategorik olasılık tahminleri için)
"""
import numpy as np
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# ─── Temel Metrikler ───

def brier_score(predictions, outcomes):
    """
    Brier Score: Tahmin ile gerçek sonuç arasındaki farkın karesi.
    Düşük = iyi. 0.25 = rastgele tahmin (50/50).

    Args:
        predictions: Tahmin olasılıkları listesi (0-1 arası)
        outcomes: Gerçek sonuçlar listesi (0 veya 1)
    Returns:
        float: Brier Score (düşük = iyi)
    """
    pred = np.array(predictions, dtype=float)
    out = np.array(outcomes, dtype=float)
    if len(pred) == 0:
        return 0.0
    return float(np.mean((pred - out) ** 2))


def log_loss(predictions, outcomes):
    """
    Log Loss (Cross-Entropy): Yanlış tahminlere ağır ceza verir.
    Düşük = iyi.

    Args:
        predictions: Tahmin olasılıkları (0-1 arası, 0'a çok yakın olmamalı)
        outcomes: Gerçek sonuçlar (0 veya 1)
    Returns:
        float: Log Loss
    """
    pred = np.clip(np.array(predictions, dtype=float), 1e-10, 1 - 1e-10)
    out = np.array(outcomes, dtype=float)
    if len(pred) == 0:
        return 0.0
    return float(-np.mean(out * np.log(pred) + (1 - out) * np.log(1 - pred)))


def accuracy(predictions, outcomes, threshold=0.5):
    """
    Accuracy: Doğru tahmin yüzdesi (ikili sınıflandırma için).

    Args:
        predictions: Tahmin olasılıkları
        outcomes: Gerçek sonuçlar (0 veya 1)
        threshold: Eşik değeri
    Returns:
        float: Accuracy (0-100 arası百分比)
    """
    pred = np.array(predictions, dtype=float)
    out = np.array(outcomes, dtype=float)
    if len(pred) == 0:
        return 0.0
    predicted_class = (pred >= threshold).astype(int)
    return float(np.mean(predicted_class == out) * 100)


# ─── Kategorik Metrikler (1X2 için) ───

def rps(predictions, outcome_idx):
    """
    Ranked Probability Score: Kategorik olasılık tahminleri için.
    1X2 tahminleri için uygundur.
    Düşük = iyi. 0.222 = rastgele tahmin (3 kategori).

    Args:
        predictions: [p_home, p_draw, p_away] olasılık listesi
        outcome_idx: Gerçek sonucun indeksi (0=home, 1=draw, 2=away)
    Returns:
        float: RPS
    """
    pred = np.array(predictions, dtype=float)
    if len(pred) != 3 or abs(sum(pred) - 1.0) > 0.01:
        logger.warning("RPS için 3 kategorili olasılık gerekli ve toplamı 1 olmalı.")
        return 0.222  # rastgele baseline

    # Kümülatif olasılıklar
    cum_pred = np.cumsum(pred)
    cum_outcome = np.zeros(3)
    cum_outcome[outcome_idx:] = 1.0

    return float(np.mean((cum_pred - cum_outcome) ** 2))


def multi_class_brier(predictions, outcome_idx):
    """
    Multi-class Brier Score.
    Her kategori için (p - actual)^2 ortalaması.

    Args:
        predictions: [p_home, p_draw, p_away] olasılık listesi
        outcome_idx: Gerçek sonucun indeksi
    Returns:
        float: Multi-class Brier (düşük = iyi, 0.444 = rastgele)
    """
    pred = np.array(predictions, dtype=float)
    actual = np.zeros(3)
    actual[outcome_idx] = 1.0
    return float(np.mean((pred - actual) ** 2))


# ─── Kalibrasyon Metrikleri ───

def expected_calibration_error(predictions, outcomes, n_bins=10):
    """
    Expected Calibration Error (ECE):
    Tahmin olasılıkları ile gözlem frekansları arasındaki fark.
    Düşük = iyi kalibre. <0.05 = çok iyi.

    Args:
        predictions: Tahmin olasılıkları
        outcomes: Gerçek sonuçlar (0 veya 1)
        n_bins: Kalibrasyon bin sayısı
    Returns:
        float: ECE
    """
    pred = np.array(predictions, dtype=float)
    out = np.array(outcomes, dtype=float)

    if len(pred) == 0:
        return 0.0

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        lower, upper = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (pred > lower) & (pred <= upper)

        if i == 0:
            mask = (pred >= lower) & (pred <= upper)

        bin_size = np.sum(mask)
        if bin_size == 0:
            continue

        bin_pred_mean = np.mean(pred[mask])
        bin_outcome_mean = np.mean(out[mask])

        ece += (bin_size / len(pred)) * abs(bin_pred_mean - bin_outcome_mean)

    return float(ece)


def maximum_calibration_error(predictions, outcomes, n_bins=10):
    """
    Maximum Calibration Error (MCE):
    En kötü kalibrasyon bin'indeki fark.
    ECE'den daha katı bir metrik.
    """
    pred = np.array(predictions, dtype=float)
    out = np.array(outcomes, dtype=float)

    if len(pred) == 0:
        return 0.0

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    mce = 0.0

    for i in range(n_bins):
        lower, upper = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (pred > lower) & (pred <= upper)
        if i == 0:
            mask = (pred >= lower) & (pred <= upper)

        bin_size = np.sum(mask)
        if bin_size == 0:
            continue

        gap = abs(np.mean(pred[mask]) - np.mean(out[mask]))
        mce = max(mce, gap)

    return float(mce)


def calibration_bins(predictions, outcomes, n_bins=10):
    """
    Kalibrasyon bin verilerini döner (grafik için).
    Her bin için tahmin ortalaması ve gerçek frekansı hesaplar.

    Returns:
        list of dict: [{"bin": str, "predicted": float, "observed": float, "count": int}]
    """
    pred = np.array(predictions, dtype=float)
    out = np.array(outcomes, dtype=float)

    if len(pred) == 0:
        return []

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

        bins.append({
            "bin": f"{lower:.1f}-{upper:.1f}",
            "predicted": round(float(np.mean(pred[mask])), 4),
            "observed": round(float(np.mean(out[mask])), 4),
            "count": bin_size,
            "gap": round(float(abs(np.mean(pred[mask]) - np.mean(out[mask]))), 4),
        })

    return bins


# ─── ROI Metrikleri ───

def calculate_roi(predictions, outcomes, odds_list, stake=1.0):
    """
    Return on Investment hesaplar.

    Args:
        predictions: Tahmin olasılıkları
        outcomes: Gerçek sonuçlar (0 veya 1)
        odds_list: Bahis oranları (decimal odds)
        stake: Birim bahis
    Returns:
        dict: {"roi": float, "total_profit": float, "total_bets": int, "wins": int}
    """
    pred = np.array(predictions, dtype=float)
    out = np.array(outcomes, dtype=float)
    odds = np.array(odds_list, dtype=float)

    if len(pred) == 0:
        return {"roi": 0, "total_profit": 0, "total_bets": 0, "wins": 0}

    total_stake = len(pred) * stake
    total_profit = 0.0
    wins = 0

    for p, o, actual in zip(pred, out, odds):
        if actual == 1:
            profit = stake * (o - 1)
            total_profit += profit
            wins += 1
        else:
            total_profit -= stake

    roi = (total_profit / total_stake) * 100 if total_stake > 0 else 0

    return {
        "roi": round(roi, 2),
        "total_profit": round(total_profit, 2),
        "total_bets": len(pred),
        "wins": wins,
        "losses": len(pred) - wins,
        "win_rate": round((wins / len(pred)) * 100, 1) if len(pred) > 0 else 0,
    }


def kelly_criterion(p, odds):
    """
    Kelly Criterion: Optimal bahis oranını hesaplar.

    Args:
        p: Tahmin olasılığı (0-1)
        odds: Decimal odds
    Returns:
        float: Kelly fraksiyonu (0-1 arası, negatifse bahis yapma)
    """
    if odds <= 1 or p <= 0 or p >= 1:
        return 0.0

    q = 1 - p
    b = odds - 1
    kelly = (b * p - q) / b

    return max(0.0, min(kelly, 1.0))


# ─── Toplu Analiz ───

def full_evaluation(predictions, outcomes, odds_list=None):
    """
    Tüm metrikleri tek seferde hesaplar.

    Args:
        predictions: [p_home, p_draw, p_away] veya [p_home] listesi
        outcomes: Gerçek sonuçlar (0/1/2 veya 0/1)
        odds_list: Opsiyonel bahis oranları
    Returns:
        dict: Tüm metrikler
    """
    pred = np.array(predictions, dtype=float)
    out = np.array(outcomes, dtype=float)

    results = {}

    if len(pred.shape) == 1 or (len(pred) > 0 and not isinstance(pred[0], (list, np.ndarray))):
        # İkili tahmin (1X2 yerine tek sonuç)
        results["brier"] = round(brier_score(pred, out), 4)
        results["log_loss"] = round(log_loss(pred, out), 4)
        results["ece"] = round(expected_calibration_error(pred, out), 4)
        results["mce"] = round(maximum_calibration_error(pred, out), 4)
        results["accuracy"] = round(accuracy(pred, out), 1)
    else:
        # 1X2 kategorik tahmin
        rps_scores = []
        for i, (p, o) in enumerate(zip(pred, out)):
            rps_scores.append(rps(p, int(o)))
        results["rps"] = round(float(np.mean(rps_scores)), 4) if rps_scores else 0.222

    if odds_list is not None and len(odds_list) > 0:
        # Sadece en yüksek olasılıklı tahminleri al
        if len(pred.shape) > 1:
            max_pred = np.max(pred, axis=1)
        else:
            max_pred = pred
        results["roi"] = calculate_roi(max_pred, out, odds_list)

    results["calibration_bins"] = calibration_bins(pred.flatten(), out.flatten())

    return results


def accuracy_by_tier(predictions, outcomes, tiers):
    """
    Her tier (PLATINUM/GOLD/SILVER/BRONZE) için ayrı accuracy hesaplar.

    Args:
        predictions: Tahmin olasılıkları
        outcomes: Gerçek sonuçlar
        tiers: Tier listesi (["PLATINUM", "GOLD", ...])
    Returns:
        dict: {tier: {"accuracy": float, "count": int, "brier": float}}
    """
    tier_data = defaultdict(lambda: {"preds": [], "outs": []})

    for pred, out, tier in zip(predictions, outcomes, tiers):
        tier_data[tier]["preds"].append(pred)
        tier_data[tier]["outs"].append(out)

    results = {}
    for tier, data in tier_data.items():
        preds = np.array(data["preds"])
        outs = np.array(data["outs"])
        results[tier] = {
            "accuracy": round(float(np.mean(preds >= 0.5) == outs) * 100, 1) if len(preds) > 0 else 0,
            "count": len(preds),
            "brier": round(brier_score(preds, outs), 4),
            "avg_confidence": round(float(np.mean(preds)), 3),
        }

    return results

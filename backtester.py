"""
Walk-Forward Backtester
Modeli gerçekçi koşullarda değerlendirir:
- Geçmiş verilerle eğit, gelecek verilerle test et (asla gelecek veriye bakma)
- Her ay/hafta bir kez yeniden eğit (rolling window)
- Sonuçları periyodik olarak kaydet

Referans: "Walk-Forward Analysis" - Pardo, R. (2008). The Evaluation and Optimization of Trading Strategies.
"""
import logging
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class WalkForwardBacktester:
    """
    Walk-forward backtesting motoru.
    Geçmiş verilerle eğiterek gelecek maçları tahmin eder.
    """

    def __init__(self, db):
        self.db = db

    def run_walk_forward(self, model, feature_builder, test_days=30, train_window_days=365,
                         retrain_interval_days=30, min_train_samples=200):
        """
        Walk-forward backtest çalıştırır.

        Args:
            model: Eğitim ve tahmin yapan model nesnesi
            feature_builder: Feature oluşturan fonksiyon (matches_df -> features_df)
            test_days: Her test periyodu kaç gün
            train_window_days: Eğitim penceresi genişliği (gün)
            retrain_interval_days: Kaç günde bir yeniden eğit
            min_train_samples: Minimum eğitim örneği sayısı
        Returns:
            dict: Backtest sonuçları
        """
        from metrics import brier_score, expected_calibration_error, accuracy, rps, calculate_roi

        logger.info(f"🔄 Walk-forward backtest başlatılıyor: "
                    f"test={test_days}g, train={train_window_days}g, retrain={retrain_interval_days}g")

        # Tüm veriyi yükle
        all_matches = self.db.get_all_matches_df()
        if all_matches is None or all_matches.empty:
            logger.error("Maç verisi bulunamadı.")
            return {"error": "Maç verisi yok"}

        # Tarih sütununu çevir
        all_matches['match_date'] = all_matches['match_date'].apply(
            lambda x: self._parse_date(x)
        )
        all_matches = all_matches.dropna(subset=['match_date'])
        all_matches = all_matches.sort_values('match_date').reset_index(drop=True)

        # Tarih aralığını belirle
        min_date = all_matches['match_date'].min()
        max_date = all_matches['match_date'].max()

        logger.info(f"📅 Veri aralığı: {min_date.strftime('%Y-%m-%d')} → {max_date.strftime('%Y-%m-%d')}")
        logger.info(f"📊 Toplam maç: {len(all_matches)}")

        # Walk-forward döngüsü
        all_predictions = []
        all_actuals = []
        all_dates = []
        all_teams_home = []
        all_teams_away = []
        all_tiers = []

        current_test_start = min_date + timedelta(days=train_window_days)
        window_id = 0

        while current_test_start < max_date:
            current_test_end = min(current_test_start + timedelta(days=test_days), max_date)
            window_id += 1

            # Eğitim verisi: test döneminden önceki train_window_days gün
            train_start = current_test_start - timedelta(days=train_window_days)
            train_mask = (all_matches['match_date'] >= train_start) & (all_matches['match_date'] < current_test_start)
            train_data = all_matches[train_mask]

            # Test verisi
            test_mask = (all_matches['match_date'] >= current_test_start) & (all_matches['match_date'] < current_test_end)
            test_data = all_matches[test_mask]

            if len(train_data) < min_train_samples:
                current_test_start = current_test_end
                continue

            if len(test_data) == 0:
                current_test_start = current_test_end
                continue

            try:
                # Modeli eğit
                model.fit_from_matches(train_data)

                # Her test maçı için tahmin et
                for _, match in test_data.iterrows():
                    home = match.get('home_team', '')
                    away = match.get('away_team', '')

                    if not home or not away:
                        continue

                    try:
                        pred = model.predict(home, away)
                        if pred is None:
                            continue

                        # Gerçek sonucu belirle
                        fthg = match.get('fthg')
                        ftag = match.get('ftag')
                        ftr = match.get('ftr', '')

                        if fthg is None or ftag is None:
                            continue

                        actual_idx = 0 if ftr == 'H' else (1 if ftr == 'D' else 2)

                        # Tahmini al
                        if isinstance(pred, dict):
                            p_home = pred.get('home_win', 0.33)
                            p_draw = pred.get('draw', 0.33)
                            p_away = pred.get('away_win', 0.33)
                        else:
                            continue

                        # Tier belirle
                        max_prob = max(p_home, p_draw, p_away)
                        if max_prob >= 0.65:
                            tier = "PLATINUM"
                        elif max_prob >= 0.53:
                            tier = "GOLD"
                        elif max_prob >= 0.42:
                            tier = "SILVER"
                        else:
                            tier = "BRONZE"

                        all_predictions.append([p_home, p_draw, p_away])
                        all_actuals.append(actual_idx)
                        all_dates.append(match['match_date'].strftime('%Y-%m-%d'))
                        all_teams_home.append(home)
                        all_teams_away.append(away)
                        all_tiers.append(tier)

                    except Exception as e:
                        continue

            except Exception as e:
                logger.error(f"Pencere {window_id} hatası: {e}")

            current_test_start = current_test_end

        if not all_predictions:
            return {"error": "Tahmin üretilmedi"}

        # Metrikleri hesapla
        pred_arr = np.array(all_predictions)
        actual_arr = np.array(all_actuals)

        # 1X2 Accuracy
        predicted_class = np.argmax(pred_arr, axis=1)
        acc = float(np.mean(predicted_class == actual_arr) * 100)

        # RPS
        rps_scores = [rps(p, int(a)) for p, a in zip(pred_arr, actual_arr)]
        avg_rps = float(np.mean(rps_scores))

        # Brier (her kategori için)
        brier_scores = []
        for i in range(3):
            binary_outcome = (actual_arr == i).astype(float)
            brier_scores.append(float(np.mean((pred_arr[:, i] - binary_outcome) ** 2)))
        avg_brier = float(np.mean(brier_scores))

        # ECE
        max_probs = np.max(pred_arr, axis=1)
        binary_correct = (predicted_class == actual_arr).astype(float)
        ece = expected_calibration_error(max_probs, binary_correct)

        # Tier bazlı accuracy
        tier_results = defaultdict(lambda: {"correct": 0, "total": 0})
        for pred, actual, tier in zip(pred_arr, actual_arr, all_tiers):
            tier_results[tier]["total"] += 1
            if np.argmax(pred) == actual:
                tier_results[tier]["correct"] += 1

        tier_accuracy = {}
        for tier, data in tier_results.items():
            tier_accuracy[tier] = {
                "accuracy": round(data["correct"] / data["total"] * 100, 1) if data["total"] > 0 else 0,
                "count": data["total"],
            }

        # ROI (basit: en yüksek olasılıklı tahmini oyna)
        max_pred = np.max(pred_arr, axis=1)
        # Basit decimal odds simülasyonu (1/p)
        simulated_odds = 1.0 / np.clip(max_pred, 0.1, 0.99)
        roi_result = calculate_roi(max_pred, binary_correct, simulated_odds)

        results = {
            "total_matches": len(all_predictions),
            "accuracy": round(acc, 1),
            "rps": round(avg_rps, 4),
            "brier": round(avg_brier, 4),
            "ece": round(ece, 4),
            "tier_accuracy": tier_accuracy,
            "roi": roi_result,
            "windows": window_id,
            "date_range": {
                "first": all_dates[0] if all_dates else "",
                "last": all_dates[-1] if all_dates else "",
            },
        }

        logger.info(f"✅ Walk-forward tamamlandı: {len(all_predictions)} maç, "
                    f"Accuracy={acc:.1f}%, RPS={avg_rps:.4f}, Brier={avg_brier:.4f}, ECE={ece:.4f}")

        return results

    def _parse_date(self, date_str):
        """Tarih stringini datetime'a çevirir."""
        if isinstance(date_str, datetime):
            return date_str
        if not isinstance(date_str, str):
            return None

        formats = ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None

    def compare_with_market(self, model, feature_builder, test_days=90):
        """
        Model ile piyasa (bookmaker) oranlarını karşılaştırır.

        Returns:
            dict: Model vs Market karşılaştırması
        """
        all_matches = self.db.get_all_matches_df()
        if all_matches is None or all_matches.empty:
            return {"error": "Veri yok"}

        all_matches['match_date'] = all_matches['match_date'].apply(lambda x: self._parse_date(x))
        all_matches = all_matches.dropna(subset=['match_date'])
        all_matches = all_matches.sort_values('match_date')

        # Son test_days günü test et
        max_date = all_matches['match_date'].max()
        test_start = max_date - timedelta(days=test_days)
        test_data = all_matches[all_matches['match_date'] >= test_start]

        market_correct = 0
        model_correct = 0
        total = 0

        for _, match in test_data.iterrows():
            home = match.get('home_team', '')
            away = match.get('away_team', '')
            ftr = match.get('ftr', '')

            if not home or not away or not ftr:
                continue

            actual_idx = 0 if ftr == 'H' else (1 if ftr == 'D' else 2)

            # Market tahmini (en yüksek orandan)
            b365h = match.get('b365h') or match.get('avgh')
            b365d = match.get('b365d') or match.get('avgd')
            b365a = match.get('b365a') or match.get('avga')

            if b365h and b365d and b365a:
                try:
                    implied_home = 1 / float(b365h)
                    implied_draw = 1 / float(b365d)
                    implied_away = 1 / float(b365a)
                    market_pred = np.argmax([implied_home, implied_draw, implied_away])
                    if market_pred == actual_idx:
                        market_correct += 1
                except (ValueError, ZeroDivisionError):
                    pass

            # Model tahmini
            try:
                pred = model.predict(home, away)
                if pred and isinstance(pred, dict):
                    model_pred = np.argmax([pred.get('home_win', 0), pred.get('draw', 0), pred.get('away_win', 0)])
                    if model_pred == actual_idx:
                        model_correct += 1
                    total += 1
            except Exception:
                continue

        return {
            "test_matches": total,
            "market_accuracy": round(market_correct / total * 100, 1) if total > 0 else 0,
            "model_accuracy": round(model_correct / total * 100, 1) if total > 0 else 0,
        }

"""
Football Data App - Scraper (CSV Tabanlı)
=========================================
İddaa bülteni çekme (mock) ve sonuçlandırma işlemlerini yapar.
SQLite bağımlılığı kaldırılmıştır.
"""

import os
import re
import json
import hashlib
import logging
import time
import urllib.request
import pandas as pd
from bs4 import BeautifulSoup
from difflib import get_close_matches
from datetime import datetime, timedelta
from analyzer import Analyzer
from bsd_api_scraper import BSDScraper

logger = logging.getLogger(__name__)

class IddaaScraper:
    def __init__(self, db, predictor):
        self.db = db
        self.predictor = predictor
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    def fetch_upcoming_matches(self, days=14):
        """Maç programı CSV'den (bsd_fixtures.csv) gelecek maçları okur."""
        bsd_scraper = BSDScraper(self.db)
        
        # Fixtures CSV'yi kontrol et, yoksa çek
        csv_path = os.path.join("data", "bsd_fixtures.csv")
        if not os.path.exists(csv_path):
            bsd_scraper.save_fixtures_csv(days=days)
        
        results = []
        try:
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                for idx, row in df.iterrows():
                    try:
                        date_str = str(row['Date'])
                        if '/' in date_str:
                            date_obj = datetime.strptime(date_str, "%d/%m/%y")
                        else:
                            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        if date_obj.date() >= datetime.now().date():
                            league_id_raw = row.get('league_id', '')
                            try:
                                league_id_val = int(float(league_id_raw)) if league_id_raw and str(league_id_raw) != 'nan' else 0
                            except (ValueError, TypeError):
                                league_id_val = 0
                            results.append({
                                'home': str(row['HomeTeam']),
                                'away': str(row['AwayTeam']),
                                'date': date_obj.strftime("%Y-%m-%d"),
                                'league': str(row.get('Div', '')),
                                'league_id': league_id_val,
                                'event_id': row.get('event_id', ''),
                                'odds': {'h': row.get('B365H', ''), 'd': row.get('B365D', ''), 'a': row.get('B365A', '')}
                            })
                    except (ValueError, KeyError) as e:
                        logger.debug(f"Satır okuma hatası: {e}")
                        continue
            logger.info(f"Fixtures CSV'den {len(results)} güncel maç çekildi.")
        except Exception as e:
            logger.error(f"BSD API CSV okuma hatası: {e}")
            
        return results

    def fetch_injuries(self, team_name):
        return "Bilinmiyor (API Bağlantısı Yok)"

    def get_weekly_predictions(self):
        """Haftalık maçları çeker ve tahmin üretir."""
        analyzer = Analyzer(self.db)
        self.predictor.load_model()
        
        raw_matches = self.fetch_upcoming_matches()
        if not raw_matches:
            return {"error": "Maç verisi çekilemedi veya bülten boş."}

        db_teams = self.db.get_teams()
        if not db_teams:
            return {"error": "Veritabanında takım yok."}

        # Takım adı eşleştirme haritası oluştur
        team_map = {}
        for t in db_teams:
            key = t.lower().strip()
            team_map[key] = t
            # Kısa isimler için de ekle
            for prefix in ['fc ', 'cf ', 'sc ', 'ss ', 'nk ', 'ac ', 'as ', 'ad ', 'ae ', 'sk ', 'fk ']:
                if key.startswith(prefix):
                    short = key[len(prefix):]
                    if short not in team_map:
                        team_map[short] = t

        team_keys = list(team_map.keys())

        tum_tahminler_batch = []
        skipped_count = 0
        success_count = 0
        error_count = 0
        BATCH_SIZE = 50

        def normalize_team_name(name):
            cleaned = name.strip()
            for prefix in ['FC ', 'CF ', 'SC ', 'SS ', 'NK ', 'AC ', 'AS ', 'AD ', 'AE ', 'SK ', 'FK ']:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):]
            for suffix in [' FC', ' CF', ' SC', ' SD', ' UD', ' CD', ' FK', ' SK', ' BK', ' IF', ' IK', ' AF', ' GF']:
                if cleaned.endswith(suffix):
                    cleaned = cleaned[:-len(suffix)]
            return cleaned.strip()

        def find_best_match(csv_name):
            normalized = normalize_team_name(csv_name)
            csv_lower = csv_name.lower().strip()
            norm_lower = normalized.lower()

            if csv_lower in team_map:
                return team_map[csv_lower]
            if norm_lower in team_map:
                return team_map[norm_lower]

            for key, val in team_map.items():
                if key == norm_lower or key == csv_lower:
                    return val

            for key, val in team_map.items():
                if key.startswith(norm_lower) or norm_lower.startswith(key):
                    return val
                if csv_lower.startswith(key) or key.startswith(csv_lower):
                    return val

            candidates = get_close_matches(norm_lower, team_keys, n=5, cutoff=0.4)
            if candidates:
                best = None
                best_score = 0
                for c in candidates:
                    score = len(set(norm_lower) & set(c)) / max(len(norm_lower), len(c), 1)
                    if score > best_score:
                        best_score = score
                        best = team_map[c]
                if best and best_score >= 0.35:
                    return best

            return None
        
        import hashlib
        loop_start = time.time()
        for idx, match in enumerate(raw_matches):
            csv_home = match['home']
            csv_away = match['away']
            
            t_match = time.time()
            db_home = find_best_match(csv_home)
            db_away = find_best_match(csv_away)
            match_elapsed = time.time() - t_match
            
            if not db_home or not db_away:
                skipped_count += 1
                continue
            
            if db_home == db_away:
                skipped_count += 1
                continue
            
            t_pred = time.time()
            pred = self.predictor.predict_match_ml(db_home, db_away, league_id=match.get('league_id', 0), match_date=match.get('date'))
            pred_elapsed = time.time() - t_pred
            
            if pred and not pred.get("error"):
                pred_id_str = f"{db_home}|{db_away}|{match.get('date','')}"
                pred_id = int(hashlib.md5(pred_id_str.encode()).hexdigest()[:12], 16)
                
                tum_tahminler_batch.append({
                    'id': match.get('id', pred_id),
                    'match_date': match.get('date', datetime.now().strftime('%Y-%m-%d')),
                    'home_team': db_home,
                    'away_team': db_away,
                    'predicted_result': pred.get("prediction"),
                    'confidence': pred.get("confidence"),
                    'goals_market': json.dumps(pred.get("goals_market", {})),
                    'win_probabilities': json.dumps(pred.get("probabilities", {})),
                    'status': 'pending',
                    'league_id': match.get('league_id', 0),
                    'model_version': 'v1.2-csv',
                    'tier': pred.get("tier"),
                    'tier_confidence': pred.get("tier_confidence"),
                    'advanced_metrics_json': json.dumps(pred.get("advanced_metrics", {})),
                    'created_at': datetime.now().isoformat()
                })
                success_count += 1
            else:
                error_count += 1
                if error_count <= 3:
                    logger.warning(f"  [{idx}] PRED ERR: {db_home} vs {db_away}: {pred}")

            if len(tum_tahminler_batch) >= BATCH_SIZE:
                self.db.save_predictions_batch(tum_tahminler_batch)
                elapsed = time.time() - loop_start
                logger.info(f"  [BATCH] {success_count} ok, {error_count} err, {skipped_count} skip, {elapsed:.1f}s, {idx+1}/{len(raw_matches)}")
                tum_tahminler_batch = []

        if tum_tahminler_batch:
            self.db.save_predictions_batch(tum_tahminler_batch)

        elapsed = time.time() - loop_start
        logger.info(f"[DONE] {success_count} preds, {error_count} errors, {skipped_count} skipped, {elapsed:.1f}s")
        return {"predictions": tum_tahminler_batch}

    def resolve_pending_predictions(self):
        """Bekleyen tahminleri BSD API üzerinden gerçek sonuçlarla eşleştirip sonuçlandırır."""
        logger.info("🏟️ Bekleyen maçlar sonuçlandırılıyor...")
        pending_preds = self.db.get_pending_predictions_full()
        if not pending_preds: 
            logger.info("✅ Bekleyen maç yok.")
            return 0
        
        # Eski pending'leri temizle (30 günden eski)
        stale_cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        stale_count = self.db.cleanup_stale_pending(stale_cutoff)
        if stale_count > 0:
            logger.info(f"🧹 {stale_count} adet 30+ günlük bekleyen tahmin temizlendi")
            pending_preds = self.db.get_pending_predictions_full()
        
        # Tarih aralığı ile toplu çek (tek tek tarih yerine)
        unique_dates = sorted(set(p['match_date'] for p in pending_preds))
        if not unique_dates:
            logger.info("✅ Bekleyen maç yok.")
            return 0
            
        min_date = unique_dates[0]
        max_date = unique_dates[-1]
        logger.info(f"📅 Tarih aralığı: {min_date} → {max_date} ({len(unique_dates)} farklı tarih)")
        
        bsd_scraper = BSDScraper(self.db)
        resolved_count = 0
        
        # Tüm tarihler için toplu çek
        all_results = []
        try:
            all_results = bsd_scraper.fetch_events(
                date_from=min_date, date_to=max_date, status="finished"
            )
            if not all_results:
                all_results = bsd_scraper.fetch_events(
                    date_from=min_date, date_to=max_date, status="FT"
                )
        except Exception as e:
            logger.error(f"Toplu sonuç çekme hatası: {e}")
        
        # Sonuçları tarihe göre grupla
        results_by_date = {}
        for event in all_results:
            if event.get("FTHG") and event.get("FTAG"):
                event_date = event.get("Date", "")
                if event_date:
                    results_by_date.setdefault(event_date, []).append({
                        "home": event.get("HomeTeam", ""),
                        "away": event.get("AwayTeam", ""),
                        "fthg": str(event["FTHG"]),
                        "ftag": str(event["FTAG"]),
                    })
        
        logger.info(f"📊 {len(all_results)} sonuç çekildi, {len(results_by_date)} tarihe dağıtıldı")
        
        # Her bekleyen tahmini sonuçlandır
        for pred in pending_preds:
            date_str = pred.get('match_date', '')
            
            # Tarihe eşleşen sonuçları al
            daily_results = results_by_date.get(date_str, [])
            
            # Tarih formatı uyumsuzluğu: YYYY-MM-DD ile de dene
            if not daily_results:
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    alt_date = dt.strftime('%d/%m/%y')
                    daily_results = results_by_date.get(alt_date, [])
                except:
                    pass
            
            if not daily_results:
                continue
            
            def is_match(p_home, p_away, r_home, r_away):
                p_home, p_away = p_home.lower(), p_away.lower()
                r_home, r_away = r_home.lower(), r_away.lower()
                
                if p_home == r_home and p_away == r_away: return True
                if p_home == r_away and p_away == r_home: return True
                
                h_match = get_close_matches(p_home, [r_home], n=1, cutoff=0.55)
                a_match = get_close_matches(p_away, [r_away], n=1, cutoff=0.55)
                return bool(h_match and a_match)

            match_result = next((r for r in daily_results if is_match(pred['home_team'], pred['away_team'], r['home'], r['away'])), None)
                
            if match_result:
                try:
                    self.db.update_prediction_result(
                        pred['id'], 
                        int(match_result['fthg']), 
                        int(match_result['ftag'])
                    )
                    resolved_count += 1

                    # Kalibrasyon verisi topla
                    try:
                        from calibrator import ModelCalibrator
                        calibrator = ModelCalibrator()
                        prediction_val = pred.get('confidence', 0.5) / 100.0 if pred.get('confidence') else 0.5
                        outcome_val = 1.0 if pred.get('is_correct') else 0.0
                        tier_raw = pred.get('tier', 'BRONZE')
                        tier_label = tier_raw.replace('💎 ', '').replace('🥇 ', '').replace('🥈 ', '').replace('🥉 ', '') if tier_raw else 'BRONZE'
                        calibrator.collect_prediction(prediction_val, outcome_val, tier=tier_label)
                    except Exception:
                        pass

                    # Self-learning: Hata analizi
                    try:
                        from self_learning import SelfLearningEngine
                        sle = SelfLearningEngine(self.db)

                        pred_data = {
                            "prediction": pred.get('prediction', ''),
                            "confidence": pred.get('confidence', 50) / 100.0 if pred.get('confidence') else 0.5,
                            "tier": tier_raw,
                            "teams": {"home": pred.get('home_team', ''), "away": pred.get('away_team', '')},
                        }
                        actual_data = {
                            "home_goals": int(match_result['fthg']),
                            "away_goals": int(match_result['ftag']),
                            "ftr": match_result.get('ftr', ''),
                        }

                        mistake = sle.analyze_mistake(pred_data, actual_data)
                        if not mistake.get("is_correct", True):
                            logger.warning(f"❌ Hata analiz edildi: {pred['home_team']} vs {pred['away_team']} — {mistake.get('mistake_detail', '')}")

                        sle.update_accuracy_trend()

                        if sle.should_retrain():
                            logger.info("🔄 Yeniden eğitim önerisi: Yeterli hata birikti")
                    except Exception:
                        pass

                    logger.info(f"✅ Sonuçlandı: {pred['home_team']} {match_result['fthg']}-{match_result['ftag']} {pred['away_team']}")
                except Exception as e:
                    logger.error(f"Güncelleme hatası ({pred['id']}): {e}")
                
        logger.info(f"🏁 Toplam {resolved_count} maç sonuçlandırıldı.")
        return resolved_count

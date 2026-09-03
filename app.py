"""
Football Data App - Flask Web Uygulaması
==========================================
Ana uygulama dosyası. API endpoint'leri ve sayfa routing'lerini içerir.
"""

import os
import json
import time
import math
import threading
import logging
import functools
from datetime import datetime
from typing import List, Dict, Any, cast
from flask import Flask, render_template, jsonify as _flask_jsonify, request
from database import Database
from fetcher import FootballDataFetcher
from analyzer import Analyzer
from predictor import Predictor
from ml_predictor import MLPredictor
from scraper import IddaaScraper
from bsd_api_scraper import BSDScraper
from auto_researcher import AutoResearcher, get_status as ar_get_status, stop as ar_stop
from config import FLASK_CONFIG

# AI Agent sistemi (opsiyonel)
try:
    from ai_agents import run_full_routine as ai_run_full, run_quick_diagnostic, GROQ_API_KEY, GROQ_MODEL
    AI_AGENTS_AVAILABLE = True
except ImportError as e:
    AI_AGENTS_AVAILABLE = False
    GROQ_API_KEY = None
    GROQ_MODEL = None
    logging.warning(f"AI Agent sistemi yuklenemedi: {e}")

# ─── Logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ─── NaN-safe JSON Provider ───
def sanitize_for_json(obj):
    """NaN, inf gibi geçersiz JSON değerlerini temizler."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(sanitize_for_json(v) for v in obj)
    return obj

# ─── API Key Auth ───
API_KEY = os.environ.get("API_KEY", "")

def require_api_key(f):
    """Kritik POST endpoint'leri için API key doğrulama decorator'ı."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
        key = request.headers.get("X-API-Key", "")
        if key != API_KEY:
            return jsonify({"error": "Geçersiz API key"}), 401
        return f(*args, **kwargs)
    return decorated

# ─── Flask App ───
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# ─── jsonify wrapper (NaN-safe) ───
def safe_jsonify(*args, **kwargs):
    """jsonify çağrısından önce NaN değerlerini temizler."""
    if args:
        return _flask_jsonify(sanitize_for_json(args[0]), **kwargs)
    return _flask_jsonify(**kwargs)

# jsonify'i globally safe_jsonify ile değiştir
jsonify = safe_jsonify

# ─── Servisler ───
db = Database()
db.connect()
db.create_tables()
db.seed_leagues_and_seasons()
logger.info("📥 BSD API geçmiş verileri aktarılıyor...")
db.import_bsd_csvs()

# Elo'ları eğit (tarihsel maçlarla)
try:
    from elo import EloSystem
    elo_system = EloSystem(db)
    all_matches_for_elo = db.get_all_matches_df()
    if all_matches_for_elo is not None and not all_matches_for_elo.empty:
        matches_list = all_matches_for_elo.to_dict('records')
        elo_system.train_from_matches(matches_list, save=True)
        logger.info(f"✅ Elo eğitimi tamamlandı: {len(elo_system.ratings)} takım")
except Exception as e:
    logger.error(f"Elo eğitimi hatası: {e}")

fetcher = FootballDataFetcher()
analyzer = Analyzer(db)
predictor = Predictor(db)
ml_predictor = MLPredictor(db)
weekly_scraper = IddaaScraper(db, ml_predictor)

def refresh_predictions():
    """Yeni bir şampiyon model seçildiğinde veya manuel istekte tahminleri tazeler."""
    logger.info("🔄 Yeni şampiyon model ile haftalık tahminler tazeleniyor...")
    try:
        weekly_scraper.get_weekly_predictions()
        logger.info("✅ Haftalık tahminler yeni model ile başarıyla güncellendi.")
    except Exception as e:
        logger.error(f"Tahmin tazeleme hatası: {e}")

auto_researcher = AutoResearcher(db, on_promotion_callback=refresh_predictions)

_verified_teams_cache = None

def get_verified_teams(force_refresh=False):
    """CSV dosyalarından taranmış doğrulanmış takım listesini döner (Cached)."""
    global _verified_teams_cache
    if force_refresh:
        _verified_teams_cache = None
        
    if _verified_teams_cache is not None:
        return _verified_teams_cache
        
    try:
        if os.path.exists("data/verified_teams.json"):
            with open("data/verified_teams.json", "r", encoding="utf-8") as f:
                _verified_teams_cache = set(json.load(f))
                return _verified_teams_cache
    except Exception as e:
        logger.error(f"Verified teams load error: {e}")
    
    _verified_teams_cache = set()
    return _verified_teams_cache

# ─── Global State for Async Updates ───
_weekly_update_lock = threading.Lock()
_is_weekly_updating = False
_weekly_update_start_time = 0

# Initialize _last_weekly_update to now if future predictions already exist in DB
# This prevents the hanging background thread from triggering on every page load
try:
    _future_count_check = db.execute_query(
        "SELECT COUNT(*) FROM predictions WHERE match_date >= date('now')"
    ).fetchone()[0]
    if _future_count_check > 0:
        _last_weekly_update = time.time()
        logger.info(f"✅ DB'de {_future_count_check} gelecek tahmin bulundu, update sıfırlandı.")
    else:
        _last_weekly_update = 0
except Exception:
    _last_weekly_update = 0



# ═══════════════════════════════════════════
#  SAYFA ROUTE'LARI
# ═══════════════════════════════════════════

@app.route("/")
def index():
    """Ana dashboard sayfası."""
    return render_template("dashboard.html")


@app.route("/league/<int:league_id>")
def league_page(league_id):
    """Lig detay sayfası."""
    league = db.get_league_by_id(league_id)
    if not league:
        return "Lig bulunamadı", 404
    return render_template("league.html", league=league)


@app.route("/team/<team_name>")
def team_page(team_name):
    """Takım detay sayfası."""
    return render_template("team.html", team_name=team_name)


@app.route("/predictor")
def predictor_page():
    """Maç tahmin analiz sayfası."""
    teams = db.get_teams()
    return render_template("predictor.html", teams=teams)


@app.route("/autoresearch")
def autoresearch_page():
    """AutoResearch — Otonom Araştırma Paneli."""
    return render_template("autoresearch.html")


# ═══════════════════════════════════════════
#  API ENDPOINT'LERİ
# ═══════════════════════════════════════════

# ─── Dashboard / Genel ───


@app.route("/api/stats")
def api_stats():
    """Genel istatistik özeti."""
    stats = db.get_stats_summary()
    return jsonify(stats)


@app.route("/api/leagues")
def api_leagues():
    """Tüm ligler listesi."""
    leagues = db.get_all_leagues()
    return jsonify(leagues)


@app.route("/api/seasons")
def api_seasons():
    """Sezon listesi."""
    seasons = db.get_seasons()
    return jsonify(seasons)


@app.route("/api/recent-matches")
def api_recent_matches():
    """Son maçlar."""
    limit = request.args.get("limit", 20, type=int)
    matches = analyzer.get_recent_matches(limit)
    return jsonify(matches)


@app.route("/api/goals-by-league")
def api_goals_by_league():
    """Lig bazında gol ortalamaları."""
    season_id = request.args.get("season_id", None, type=int)
    data = analyzer.get_goals_by_league(season_id)
    return jsonify(data)


# ─── Lig API ───

@app.route("/api/league/<int:league_id>/table")
def api_league_table(league_id):
    """Lig puan tablosu."""
    season_id = request.args.get("season_id", None, type=int)
    table = db.get_league_table(league_id, season_id)
    return jsonify(table)


@app.route("/api/league/<int:league_id>/matches")
def api_league_matches(league_id):
    """Lig maçları."""
    season_id = request.args.get("season_id", None, type=int)
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    matches = db.get_matches(league_id=league_id, season_id=season_id, limit=limit, offset=offset)
    return jsonify(matches)


@app.route("/api/league/<int:league_id>/goal-stats")
def api_league_goal_stats(league_id):
    """Lig gol istatistikleri."""
    season_id = request.args.get("season_id", None, type=int)
    stats = analyzer.get_league_goal_stats(league_id, season_id)
    return jsonify(stats)


@app.route("/api/league/<int:league_id>/teams")
def api_league_teams(league_id):
    """Lig takımları."""
    teams = db.get_teams(league_id)
    return jsonify(teams)


@app.route("/api/league/<int:league_id>/odds")
def api_league_odds(league_id):
    """Lig oran analizi."""
    season_id = request.args.get("season_id", None, type=int)
    odds = analyzer.get_odds_analysis(league_id, season_id)
    return jsonify(odds)


# ─── Takım API ───

@app.route("/api/team/<team_name>/stats")
def api_team_stats(team_name):
    """Takım istatistikleri."""
    league_id = request.args.get("league_id", None, type=int)
    season_id = request.args.get("season_id", None, type=int)
    stats = analyzer.get_team_stats(team_name, league_id, season_id)
    if not stats:
        return jsonify({"error": "Takım bulunamadı"}), 404
    return jsonify(stats)


@app.route("/api/team/<team_name>/form")
def api_team_form(team_name):
    """Takım form analizi."""
    last_n = request.args.get("last_n", 10, type=int)
    league_id = request.args.get("league_id", None, type=int)
    season_id = request.args.get("season_id", None, type=int)
    form = analyzer.get_team_form(team_name, last_n, league_id, season_id)
    return jsonify(form)


@app.route("/api/team/<team_name>/matches")
def api_team_matches(team_name):
    """Takım maçları."""
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    matches = db.get_matches(team=team_name, limit=limit, offset=offset)
    return jsonify(matches)


@app.route("/api/h2h/<team1>/<team2>")
def api_h2h(team1, team2):
    """İki takım arası karşılaşma geçmişi."""
    league_id = request.args.get("league_id", None, type=int)
    h2h = analyzer.get_head_to_head(team1, team2, league_id)
    return jsonify(h2h)

@app.route("/api/predict/<team1>/<team2>")
def api_predict(team1, team2):
    """Gelecek maç tahmini (Poisson + ML Hybrid)."""
    league_id = request.args.get("league_id", None, type=int)
    season_id = request.args.get("season_id", None, type=int)
    
    # İstatistiksel / Opsiyonel Poisson Tahmini
    prediction = predictor.predict_match(team1, team2, league_id, season_id)
    if not prediction:
         return jsonify({"error": "Yeterli veri yok"}), 404
         
    # Makine Öğrenmesi Tahmini
    ml_pred = ml_predictor.predict_match_ml(team1, team2)
    
    # ML aktif ve başarılıysa tahminleri ML ile değiştir (Ensemble üstünlüğü)
    if ml_pred and not ml_pred.get("error"):
        prediction["ml_active"] = True
        prediction["win_probabilities"] = {
            "home_win": ml_pred["probabilities"].get("home", 0),
            "draw": ml_pred["probabilities"].get("draw", 0),
            "away_win": ml_pred["probabilities"].get("away", 0)
        }
        if "goals_market" in ml_pred and "over_25" in ml_pred["goals_market"]:
            prediction["goals_market"]["over_25"] = ml_pred["goals_market"]["over_25"]
            prediction["goals_market"]["under_25"] = round(100 - ml_pred["goals_market"]["over_25"], 1)
        
        prediction["tier"] = ml_pred.get("tier")
        prediction["tier_confidence"] = ml_pred.get("tier_confidence")
        prediction["advanced_metrics"] = ml_pred.get("advanced_metrics")
    else:
        prediction["ml_active"] = False
        prediction["ml_error"] = ml_pred.get("error", "Bilinmeyen ML Hatasi") if ml_pred else "ML modeli yuklenemedi"

    # Harici kaynaklardan ELO ve xG zenginlestirmesi
    try:
        from external_data_integrator import enrich_prediction_with_external
        prediction = enrich_prediction_with_external(db, prediction)
    except Exception:
        pass

    return jsonify(prediction)


# ─── Takım Arama ───

@app.route("/api/teams/search")
def api_search_teams():
    """Takım arama."""
    q = request.args.get("q", "")
    if len(q) < 2:
        return jsonify([])
    teams: List[str] = db.get_teams()
    filtered_teams: List[str] = [t for t in teams if q.lower() in t.lower()]
    # IDE'nin dilimleme (slice) hatasını (False Positive) gidermek için döngü ile sınırlandırılmıştır.
    results = [filtered_teams[i] for i in range(min(len(filtered_teams), 20))]
    return jsonify(results)


# ─── Haftalık Bülten ───

@app.route("/weekly")
def weekly_page():
    """Haftalık iDdaa Bülteni ve Kupon Önerileri Sayfası."""
    return render_template("weekly.html")

@app.route("/api/weekly")
def api_weekly():
    """Haftalık maçları DB'den döner, gerekirse arka planda güncellemeyi tetikler."""
    global _is_weekly_updating, _last_weekly_update
    
    try:
        # 1. Mevcut tahminleri DB'den al (Hızlı)
        stats = db.get_prediction_accuracy_stats()
        verified = get_verified_teams()
        
        # Sadece gelecekteki maçları filtrele (tarih formatları farklı olabilir: DD/MM/YY veya YYYY-MM-DD)
        now_str = datetime.now().strftime("%Y-%m-%d")
        now_dmy = datetime.now().strftime("%d/%m/%y")
        upcoming = []
        for p in stats["history"]:
            md = p.get("match_date", "")
            # Her iki formatı da kabul et
            is_future = False
            if md:
                if "/" in md:
                    # DD/MM/YY formatı — today'den büyük veya eşit mi?
                    is_future = md >= now_dmy
                else:
                    # YYYY-MM-DD formatı
                    is_future = md >= now_str
            if is_future:
                # JSON stringleri parse et
                for col in ["goals_market", "win_probabilities", "advanced_metrics_json"]:
                    if isinstance(p.get(col), str):
                        try:
                            # advanced_metrics_json field is named advanced_metrics_json in DB but should be advanced_metrics in UI item
                            parsed = json.loads(p[col])
                            if col == "advanced_metrics_json":
                                p["advanced_metrics"] = parsed
                            else:
                                p[col] = parsed
                        except json.JSONDecodeError:
                            logger.debug(f"JSON parse hatası ({col}): {p.get(col)[:50]}...")
                            p[col] = {}
                    elif p.get(col) is None:
                        p[col] = {}
                
                # CSV verisi kontrolü
                p["home_has_csv"] = p["home_team"] in verified
                p["away_has_csv"] = p["away_team"] in verified
                p["has_csv_data"] = p["home_has_csv"] and p["away_has_csv"]
                
                upcoming.append(p)
        
        # 2. Eğer veri yoksa veya eskiyse (1 saat) arka planda güncelleme başlat
        # Mevcut gelecek tahminler varsa tetikleme
        should_update = len(upcoming) == 0 and (time.time() - _last_weekly_update > 3600)
        
        # 10 dakikadan uzun süredir updating ise sıfırla (kilit çökmüş olabilir)
        if _is_weekly_updating and _weekly_update_start_time > 0 and (time.time() - _weekly_update_start_time > 600):
            logger.warning("⚠️ Weekly update 10dk+ sürüyor, sıfırlanıyor...")
            _is_weekly_updating = False
        
        if should_update and not _is_weekly_updating:
            _is_weekly_updating = True
            _weekly_update_start_time = time.time()
            
            def background_update():
                global _is_weekly_updating, _last_weekly_update
                try:
                    logger.info("Arka planda haftalık bülten güncelleniyor...")
                    bsd_scraper_obj = BSDScraper(db)
                    bsd_scraper_obj.save_fixtures_csv(days=14)
                    weekly_scraper.get_weekly_predictions()
                    _last_weekly_update = time.time()
                    logger.info("Arka plan güncellemesi tamamlandı.")
                except Exception as e:
                    logger.error(f"Arka plan güncelleme hatası: {e}", exc_info=True)
                finally:
                    _is_weekly_updating = False

            threading.Thread(target=background_update, daemon=True).start()

        return jsonify({
            "predictions": upcoming,
            "accuracy_stats": stats,
            "is_updating": _is_weekly_updating,
            "last_update": datetime.fromtimestamp(_last_weekly_update).strftime("%H:%M:%S") if _last_weekly_update > 0 else "Hiç"
        })
        
    except Exception as e:
        logger.error(f"Weekly API Error: {e}", exc_info=True)
        return jsonify({"error": "Sunucu hatası oluştu"}), 500


# ─── Maç Programı ve Sonuçları ───

@app.route("/fixtures")
def fixtures_page():
    """Maç Programı sayfası."""
    return render_template("fixtures.html")


@app.route("/api/fixtures")
def api_fixtures():
    """Maç programını CSV'den döner, yoksa çeker."""
    bsd_scraper_obj = BSDScraper(db)
    fixtures = bsd_scraper_obj.get_fixtures_from_csv()

    if not fixtures:
        bsd_scraper_obj.save_fixtures_csv(days=14)
        fixtures = bsd_scraper_obj.get_fixtures_from_csv()

    return jsonify(fixtures)


@app.route("/api/fixtures/refresh", methods=["POST"])
def api_fixtures_refresh():
    """Maç programını BSD API'den yeniler."""
    bsd_scraper_obj = BSDScraper(db)
    success = bsd_scraper_obj.save_fixtures_csv(days=14)
    count = len(bsd_scraper_obj.get_fixtures_from_csv())
    return jsonify({"success": success, "count": count})


@app.route("/results")
def results_page():
    """Maç Sonuçları sayfası."""
    return render_template("results.html")


@app.route("/api/results")
def api_results():
    """Maç sonuçlarını CSV'den döner, yoksa çeker."""
    bsd_scraper_obj = BSDScraper(db)
    results = bsd_scraper_obj.get_results_from_csv()

    if not results:
        bsd_scraper_obj.save_results_csv(days=14)
        results = bsd_scraper_obj.get_results_from_csv()

    return jsonify(results)


@app.route("/api/results/refresh", methods=["POST"])
def api_results_refresh():
    """Maç sonuçlarını BSD API'den yeniler."""
    bsd_scraper_obj = BSDScraper(db)
    success = bsd_scraper_obj.save_results_csv(days=14)
    count = len(bsd_scraper_obj.get_results_from_csv())
    return jsonify({"success": success, "count": count})


# ─── PredixSport Tahminleri ───

@app.route("/predixsport")
def predixsport_page():
    """PredixSport AI Tahminleri sayfası."""
    return render_template("predixsport.html")


@app.route("/api/predixsport/predictions")
def api_predixsport_predictions():
    """PredixSport tahminlerini CSV'den döner, yoksa çeker."""
    from predixsport_scraper import PredixSportScraper
    scraper = PredixSportScraper()

    csv_path = os.path.join("data", "predixsport_predictions.csv")
    if os.path.exists(csv_path):
        import pandas as pd
        df = pd.read_csv(csv_path)
        predictions = df.to_dict("records")
    else:
        predictions = scraper.save_predictions_csv()

    return jsonify(predictions)


@app.route("/api/predixsport/refresh", methods=["POST"])
def api_predixsport_refresh():
    """PredixSport tahminlerini yeniler."""
    from predixsport_scraper import PredixSportScraper
    scraper = PredixSportScraper()
    predictions = scraper.save_predictions_csv()
    return jsonify({"success": True, "count": len(predictions)})


@app.route("/api/predixsport/sports")
def api_predixsport_sports():
    """PredixSport mevcut spor dallarını listeler."""
    from predixsport_scraper import PredixSportScraper
    scraper = PredixSportScraper()
    sports = scraper.list_sports()
    return jsonify(sports or {})


@app.route("/api/predictions/delete", methods=["POST"])
@require_api_key
def api_prediction_delete():
    data = request.json
    pred_id = data.get("id")
    if not pred_id: return jsonify({"error": "ID eksik"}), 400
    
    success = db.delete_prediction(pred_id)
    return jsonify({"success": success})

@app.route("/api/predictions/update", methods=["POST"])
@require_api_key
def api_prediction_update():
    data = request.json
    pred_id = data.get("id")
    home_score = data.get("home_score")
    away_score = data.get("away_score")
    
    if not pred_id or home_score is None or away_score is None:
        return jsonify({"error": "Eksik veri"}), 400
    
    success = db.update_prediction_result(pred_id, home_score, away_score)
    return jsonify({"success": success})

@app.route("/api/weekly/refresh", methods=["POST"])
def api_weekly_refresh():
    """Haftalık bülteni ve analizleri manuel olarak tetikler."""
    global _is_weekly_updating, _last_weekly_update, _weekly_update_start_time
    
    if _is_weekly_updating:
        return jsonify({"ok": False, "message": "Güncelleme zaten devam ediyor."}), 400
    
    _is_weekly_updating = True
    _weekly_update_start_time = time.time()
    
    def background_refresh():
        global _is_weekly_updating, _last_weekly_update, _weekly_update_start_time
        try:
            logger.info("[MANUEL TETİK] Fixtures güncelleniyor...")
            bsd_scraper_obj = BSDScraper(db)
            bsd_scraper_obj.save_fixtures_csv(days=14)
            logger.info("[MANUEL TETİK] Otonom analiz başlatıldı...")
            weekly_scraper.get_weekly_predictions()
            _last_weekly_update = time.time()
            logger.info("[MANUEL TETİK] Analiz tamamlandı.")
            
            # Biten maçların sonuçlarını otomatik çöz
            logger.info("Biten maçlar sonuçlandırılıyor...")
            weekly_scraper.resolve_pending_predictions()
            # Eksik goals_market verilerini tamamla
            logger.info("Eksik Over 2.5 verileri tamamlanıyor...")
            db.backfill_missing_goals_market(ml_predictor=weekly_scraper.predictor)
        except Exception as e:
            logger.error(f"Refresh Hatası: {e}", exc_info=True)
        finally:
            _is_weekly_updating = False

    threading.Thread(target=background_refresh, daemon=True).start()
    return jsonify({"ok": True, "message": "Otonom analiz arka planda başlatıldı."})


# ─── Başarı Analizi ───

@app.route("/accuracy")
def accuracy_page():
    """Geçmiş tahminlerin başarı oranlarının sergilendiği sayfa."""
    return render_template("accuracy.html")

@app.route("/api/accuracy")
def api_accuracy():
    """Başarı analizi istatistiklerini döner."""
    try:
        # Sayfa açıldığında sonuçlandırmayı tetikle
        weekly_scraper.resolve_pending_predictions()
        stats = db.get_prediction_accuracy_stats()
        
        # Modelin en son ne zaman eğitildiğini ekle
        if os.path.exists(ml_predictor.model_path):
            mtime = os.path.getmtime(ml_predictor.model_path)
            stats["last_train"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        else:
            stats["last_train"] = "Henüz eğitilmedi"
            
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Accuracy API Error: {e}", exc_info=True)
        return jsonify({"error": "İstatistikler hesaplanırken hata oluştu"}), 500


@app.route("/api/calibration")
def api_calibration():
    """Kalibrasyon analizi ve rapor döner."""
    try:
        weekly_scraper.resolve_pending_predictions()
        stats = db.get_prediction_accuracy_stats()

        all_preds = []
        all_outcomes = []
        for tier_stat in stats.get("by_tier", {}).values():
            all_preds.extend(tier_stat.get("avg_confidence_list", []))
            all_outcomes.extend([1] * int(tier_stat.get("correct", 0)) + [0] * int(tier_stat.get("wrong", 0)))

        if not all_preds:
            return jsonify({"error": "Yeterli tahmin verisi yok"}), 404

        from calibrator import ModelCalibrator
        calibrator = ModelCalibrator()
        report = calibrator.export_calibration_report(all_preds, all_outcomes)

        return jsonify(report)
    except Exception as e:
        logger.error(f"Calibration API Error: {e}", exc_info=True)
        return jsonify({"error": "Kalibrasyon analizi hesaplanırken hata oluştu"}), 500


# ─── Model Yönetimi (Self-Learning) ───

@app.route("/api/model/train", methods=["POST"])
@require_api_key
def api_model_train():
    """Yapay Zeka modelini yeni verilerle (historical + predictions_history) yeniden eğitir."""

    try:
        def run_training():
            try:
                logger.info("🧠 Model yeniden eğitimi arka planda başlatıldı...")
                success = ml_predictor.train_model()
                if success:
                    logger.info("✅ Model başarıyla güncellendi.")
                else:
                    logger.error("❌ Model eğitimi başarısız oldu.")
            except Exception as e:
                logger.error(f"Eğitim hatası: {e}")

        # Arka planda çalıştır
        thread = threading.Thread(target=run_training, daemon=True)
        thread.start()
        
        return jsonify({"message": "Eğitim işlemi başlatıldı", "status": "started"})
    except Exception as e:
        logger.error(f"Model train API Error: {e}", exc_info=True)
        return jsonify({"error": "Eğitim başlatılamadı"}), 500


@app.route("/api/self-learning/summary")
def api_self_learning_summary():
    """Self-learning durumu özeti."""
    try:
        from self_learning import SelfLearningEngine
        sle = SelfLearningEngine(db)
        summary = sle.get_learning_summary()
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Self-learning summary error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/self-learning/errors")
def api_self_learning_errors():
    """Hata analizi raporu."""
    try:
        from self_learning import SelfLearningEngine
        sle = SelfLearningEngine(db)
        report = sle.generate_error_report()
        return jsonify(report)
    except Exception as e:
        logger.error(f"Self-learning errors error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/self-learning/reset", methods=["POST"])
def api_self_learning_reset():
    """Self-learning durumunu sıfırlar."""
    try:
        from self_learning import SelfLearningEngine
        sle = SelfLearningEngine(db)
        sle.reset()
        return jsonify({"message": "Self-learning durumu sıfırlandı"})
    except Exception as e:
        logger.error(f"Self-learning reset error: {e}")
        return jsonify({"error": str(e)}), 500


# ─── Profesyonel Dashboard ───────────────────────────────────────

@app.route("/pro-dashboard")
def pro_dashboard():
    """Profesyonel analiz dashboard'u."""
    return render_template("pro_dashboard.html")


@app.route("/api/dashboard/calibration")
def api_dashboard_calibration():
    """Kalibrasyon analizi verisi."""
    try:
        stats = db.get_prediction_accuracy_stats()
        history = stats.get("history", [])

        if not history:
            return jsonify({"error": "Veri yok"}), 404

        # History'den tahmin ve sonuç çıkar
        all_preds = []
        all_outcomes = []
        for row in history:
            conf = row.get("confidence", 50)
            if conf and isinstance(conf, (int, float)):
                all_preds.append(conf / 100.0)
                all_outcomes.append(1 if row.get("status") == "won" else 0)

        if not all_preds:
            return jsonify({"error": "Veri yok"}), 404

        from calibrator import ModelCalibrator
        calibrator = ModelCalibrator()
        analysis = calibrator.analyze_calibration(all_preds, all_outcomes)
        offsets = calibrator.get_calibration_offsets(all_preds, all_outcomes)

        return jsonify({"analysis": analysis, "offsets": offsets})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboard/roi")
def api_dashboard_roi():
    """ROI analizi verisi."""
    try:
        predictions = db.get_resolved_predictions_for_training()
        if not predictions:
            return jsonify({"error": "Veri yok"}), 404

        # Varsayılan oranlar (tahmin edilen sonuca göre standart piyasa)
        DEFAULT_ODDS = {"1": 2.0, "X": 3.3, "2": 2.8}

        total_investment = len(predictions) * 100
        total_return = 0
        tier_roi = {}
        confidence_bins = {}

        for p in predictions:
            pred = p.get("predicted_result", "")
            conf = p.get("confidence", 50) or 50
            is_correct = p.get("status") == "won"
            tier = p.get("tier", "BRONZE") or "BRONZE"

            odds = DEFAULT_ODDS.get(pred, 2.0)

            if is_correct:
                total_return += 100 * odds

            if tier not in tier_roi:
                tier_roi[tier] = {"investment": 0, "return": 0, "count": 0}
            tier_roi[tier]["investment"] += 100
            tier_roi[tier]["count"] += 1
            if is_correct:
                tier_roi[tier]["return"] += 100 * odds

            conf_val = conf / 100.0 if isinstance(conf, (int, float)) else 0.5
            bin_key = f"{int(conf_val*10)//10*10}-{int(conf_val*10)//10*10+10}"
            if bin_key not in confidence_bins:
                confidence_bins[bin_key] = {"correct": 0, "total": 0}
            confidence_bins[bin_key]["total"] += 1
            if is_correct:
                confidence_bins[bin_key]["correct"] += 1

        overall_roi = ((total_return - total_investment) / total_investment * 100) if total_investment > 0 else 0

        for tier in tier_roi:
            t = tier_roi[tier]
            t["roi"] = round(((t["return"] - t["investment"]) / t["investment"] * 100) if t["investment"] > 0 else 0, 1)

        for b in confidence_bins:
            cb = confidence_bins[b]
            cb["accuracy"] = round(cb["correct"] / cb["total"] * 100, 1) if cb["total"] > 0 else 0

        return jsonify({
            "overall_roi": round(overall_roi, 1),
            "total_predictions": len(predictions),
            "tier_roi": tier_roi,
            "confidence_bins": confidence_bins,
            "total_investment": total_investment,
            "total_return": round(total_return, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboard/errors")
def api_dashboard_errors():
    """Hata analizi dashboard verisi."""
    try:
        from self_learning import SelfLearningEngine
        sle = SelfLearningEngine(db)
        report = sle.generate_error_report()
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboard/learning")
def api_dashboard_learning():
    """Self-learning durumu dashboard verisi."""
    try:
        from self_learning import SelfLearningEngine
        sle = SelfLearningEngine(db)
        summary = sle.get_learning_summary()
        trend = sle.get_accuracy_trend()
        return jsonify({"summary": summary, "trend": trend})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── AutoResearch API ───────────────────────────────────────────

@app.route("/api/autoresearch/start", methods=["POST"])
@require_api_key
def api_ar_start():
    """Otonom araştırma döngüsünü başlatır."""
    state = ar_get_status()
    if state["running"]:
        return jsonify({"ok": False, "message": "Araştırma zaten çalışıyor."})

    data = request.get_json(silent=True) or {}
    n_exp    = int(data.get("n_experiments", 20))
    budget   = float(data.get("time_budget_min", 60))

    auto_researcher.start_background(n_experiments=n_exp, time_budget_min=budget)
    return jsonify({"ok": True, "message": f"{n_exp} deney, {budget} dk limit ile araştırma başlatıldı."})


@app.route("/api/autoresearch/stop", methods=["POST"])
@require_api_key
def api_ar_stop():
    """Araştırma döngüsünü durdurur."""
    ar_stop()
    return jsonify({"ok": True, "message": "Durdurma sinyali gönderildi."})


@app.route("/api/autoresearch/status")
def api_ar_status():
    """Mevcut araştırma durumunu döndürür."""
    return jsonify(ar_get_status())


@app.route("/api/autoresearch/results")
def api_ar_results():
    """Tüm deney sonuçlarını ve champion'ı döndürür."""
    experiments = db.get_experiments(limit=200)
    champion    = db.get_champion_experiment()
    return jsonify({"experiments": experiments, "champion": champion})


@app.route("/api/autoresearch/promote", methods=["POST"])
@require_api_key
def api_ar_promote():
    """Champion deneyi aktif ML modeline promote eder."""
    def run_promote():
        auto_researcher.promote_champion()
    threading.Thread(target=run_promote, daemon=True).start()
    return jsonify({"ok": True, "message": "Champion modeli eğitiliyor. Bu birkaç dakika sürebilir."})


# ─── Veri İndirme ───

@app.route("/api/fetch", methods=["POST"])
@require_api_key
def api_fetch():
    """Veri indirmeyi başlatır (arka planda)."""
    if fetcher.status["in_progress"]:
        return jsonify({"error": "İndirme zaten devam ediyor"}), 409

    req_data = request.get_json(silent=True) or {}
    only_latest = req_data.get("only_latest", False)

    def run_fetch(only_latest_flag):
        try:
            fetcher.fetch_all(only_latest_season=only_latest_flag)
            # İndirme tamamlandıktan sonra veritabanına aktar
            logger.info("📦 CSV dosyaları veritabanına aktarılıyor...")
            db.import_all_csvs(only_latest_season=only_latest_flag)
            
            # Takım listesini tazele (Yeni takımlar gelmiş olabilir)
            from utils.team_utils import update_verified_teams
            update_verified_teams()
            get_verified_teams(force_refresh=True)
            
            logger.info("✅ Tüm veriler aktarıldı!")
        except Exception as e:
            logger.error(f"❌ Hata: {e}")

    thread = threading.Thread(target=run_fetch, args=(only_latest,), daemon=True)
    thread.start()

    return jsonify({"message": "İndirme başlatıldı", "status": "started"})


@app.route("/api/fetch/status")
def api_fetch_status():
    """İndirme durumunu döndürür."""
    status = fetcher.get_status()
    return jsonify(status)


@app.route("/api/import", methods=["POST"])
@require_api_key
def api_import():
    """Mevcut CSV dosyalarını veritabanına aktarır."""
    def run_import():
        try:
            db.import_all_csvs()
        except Exception as e:
            logger.error(f"❌ Import hatası: {e}")

    thread = threading.Thread(target=run_import, daemon=True)
    thread.start()

    return jsonify({"message": "Import başlatıldı"})


@app.route("/api/downloaded-files")
def api_downloaded_files():
    """İndirilmiş dosyaları listeler."""
    files = fetcher.get_downloaded_files()
    return jsonify(files)


# ═══════════════════════════════════════════
#  UYGULAMA BAŞLATMA VE ARKA PLAN GÖREVLERİ
# ═══════════════════════════════════════════

def _autonomous_daily_updater():
    """
    Otonom günlük veri güncelleme sistemi.
    - Başlangıçta hemen çalışır
    - Her 30 dk'da bir zamanı kontrol eder
    - Sabah 09:00-09:30 ve akşam 19:00-19:30 aralığında tam rutin çalıştırır
    - Her rutin sonunda durum özetini loglar
    - Hatalarda 3 kez yeniden dener
    """
    last_run_date = None
    runs_today = 0
    MAX_RETRIES = 3

    def run_with_retry(func, name, retries=MAX_RETRIES):
        """Bir fonksiyonu hata durumunda yeniden dener."""
        for attempt in range(retries):
            try:
                result = func()
                return result
            except Exception as e:
                wait = 2 ** attempt * 5
                logger.warning(f"⚠️ {name} hatası (deneme {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(wait)
        logger.error(f"❌ {name} {retries} deneme sonrası başarısız.")
        return None

    def run_full_routine():
        """Tam otonom rutin: sonuçları çözümle → veri çek → tahmin üret."""
        stats = {"resolved": 0, "fixtures": 0, "results": 0, "predictions": 0, "errors": []}

        # 1. Bekleyen tahminleri çözümle
        try:
            resolved = weekly_scraper.resolve_pending_predictions()
            stats["resolved"] = resolved or 0
        except Exception as e:
            stats["errors"].append(f"resolve: {e}")

        # 2. BSD API'den güncel verileri çek
        try:
            bsd = BSDScraper(db)
            run_with_retry(lambda: bsd.save_fixtures_csv(days=14), "fixtures_csv")
            run_with_retry(lambda: bsd.save_results_csv(days=14), "results_csv")
        except Exception as e:
            stats["errors"].append(f"bsd_fetch: {e}")

        # 2b. Eksik takım verilerini alternatif kaynaklardan tamamla
        try:
            from auto_updater import run_auto_update
            run_with_retry(lambda: run_auto_update(db, import_to_db=True), "auto_updater")
        except Exception as e:
            stats["errors"].append(f"auto_updater: {e}")

        # 2c. Harici kaynaklar: Understat xG + ClubElo
        try:
            from external_data_integrator import run_external_data_sync
            run_with_retry(lambda: run_external_data_sync(db), "external_data")
        except Exception as e:
            stats["errors"].append(f"external_data: {e}")

        # 3. Tahmin üret
        try:
            weekly_scraper.get_weekly_predictions()
            stats["predictions"] = 1
        except Exception as e:
            stats["errors"].append(f"predictions: {e}")

        # Durum özeti
        if stats["errors"]:
            logger.warning(f"⚠️ [OTONOM] Rutin tamamlandı ({len(stats['errors'])} hata): {stats['errors']}")
        else:
            logger.info(f"✅ [OTONOM] Rutin başarıyla tamamlandı. "
                       f"Çözülen: {stats['resolved']}, Tahminler: {'üretildi' if stats['predictions'] else 'hata'}")

        # 4. AI Agent rutini (opsiyonel)
        if AI_AGENTS_AVAILABLE:
            try:
                logger.info("🤖 [OTONOM] AI Agent rutini başlatılıyor...")
                ai_run_full()
                logger.info("✅ [OTONOM] AI Agent rutini tamamlandı.")
            except Exception as e:
                logger.warning(f"⚠️ [OTONOM] AI Agent hatası (kritik değil): {e}")

        return stats

    # Ayrı bir thread'de hemen başlat
    threading.Thread(target=run_full_routine, daemon=True, name="autonomous-startup").start()

    while True:
        try:
            now = datetime.now()

            # Yeni günde sayacı sıfırla
            if last_run_date != now.date():
                last_run_date = now.date()
                runs_today = 0

            # Sabah 09:00-09:30 ve akşam 19:00-19:30 aralığında çalıştır
            in_morning_window = now.hour == 9 and now.minute < 30
            in_evening_window = now.hour == 19 and now.minute < 30

            should_run = False
            if in_morning_window and runs_today == 0:
                should_run = True
                logger.info("🌅 [OTONOM] Sabah rutini başlıyor...")
            elif in_evening_window and runs_today <= 1:
                should_run = True
                logger.info("🌆 [OTONOM] Akşam rutini başlıyor...")

            if should_run:
                run_full_routine()
                runs_today += 1

        except Exception as e:
            logger.error(f"❌ [OTONOM] Döngü hatası: {e}")

        # 30 dakikada bir zamanı kontrol et
        time.sleep(1800)


# ═══════════════════════════════════════════
#  AI AGENT API ENDPOINTS
# ═══════════════════════════════════════════

@app.route("/api/ai-agents/run", methods=["POST"])
def api_run_ai_agents():
    """AI Agent rutinini manuel olarak tetikler."""
    if not AI_AGENTS_AVAILABLE:
        return _flask_jsonify({"error": "AI Agent sistemi yüklü değil"}), 503

    mode = request.args.get("mode", "full")

    def run_in_background():
        try:
            if mode == "diagnostic":
                run_quick_diagnostic()
            else:
                ai_run_full()
        except Exception as e:
            logger.error(f"AI Agent manuel çalıştırma hatası: {e}")

    threading.Thread(target=run_in_background, daemon=True, name="ai-agents-manual").start()
    return _flask_jsonify({"status": "started", "mode": mode})


@app.route("/api/ai-agents/status", methods=["GET"])
def api_ai_agents_status():
    """AI Agent sistemi durumunu döner."""
    return _flask_jsonify({
        "available": AI_AGENTS_AVAILABLE,
        "groq_key_set": bool(GROQ_API_KEY),
        "model": GROQ_MODEL if AI_AGENTS_AVAILABLE else None,
    })


def _start_background_tasks_if_needed():
    """Uygulama başlarken sürekli otonom araştırma ve günlük görevleri başlatır."""
    # Sadece Werkzeug worker process'inde çalışmasını sağlar (master twice çalıştırmasın diye)
    # Render veya düşük bellekli ortamlarda arka plan görevlerini isteğe bağlı yap
    enable_bg = os.environ.get("ENABLE_BACKGROUND_TASKS", "False").lower() == "true"
    
    if (os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug) and enable_bg:
        logger.info("⚡ Arka plan hizmetleri ve otonom laboratuvar başlatılıyor...")
        
        # Otonom Model Geliştirme AI (AutoResearcher)
        auto_researcher.start_background(continuous=True)
        
        # Günlük Otomatik Veri Güncelleme ve Sonuçlandırma
        threading.Thread(target=_autonomous_daily_updater, daemon=True).start()
    else:
        logger.info("💤 Arka plan hizmetleri devre dışı (ENABLE_BACKGROUND_TASKS=False).")
        
        # ⚡ Başlangıçta eksik Over 2.5 verilerini tamamla ve takım listesini güncelle
        def _startup_backfill():
            time.sleep(5)  # App tamamen yüklensin
            try:
                from utils.team_utils import update_verified_teams
                update_verified_teams()
                get_verified_teams(force_refresh=True)
                
                logger.info("🔧 [BAŞLANGIÇ] Eksik Over 2.5 verileri kontrol ediliyor...")
                db.backfill_missing_goals_market(ml_predictor=weekly_scraper.predictor)
            except Exception as e:
                logger.error(f"Başlangıç backfill hatası: {e}")
        
        threading.Thread(target=_startup_backfill, daemon=True).start()

_start_background_tasks_if_needed()

if __name__ == "__main__":
    print("""
    ==========================================
        Football Data App                 
        http://127.0.0.1:5000                 
    ==========================================
    """)
    app.run(
        host=FLASK_CONFIG["host"],
        port=FLASK_CONFIG["port"],
        debug=FLASK_CONFIG["debug"]
    )

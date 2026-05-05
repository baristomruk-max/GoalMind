"""
Football Data App - Flask Web Uygulaması
==========================================
Ana uygulama dosyası. API endpoint'leri ve sayfa routing'lerini içerir.
"""

import os
import json
import time
import threading
import logging
from datetime import datetime
from typing import List, Dict, Any, cast
from flask import Flask, render_template, jsonify, request
from database import Database
from fetcher import FootballDataFetcher
from analyzer import Analyzer
from predictor import Predictor
from ml_predictor import MLPredictor
from scraper import IddaaScraper
from auto_researcher import AutoResearcher, get_status as ar_get_status, stop as ar_stop
from config import FLASK_CONFIG

# ─── Logging ───
from espn_fetcher import EspnResultsFetcher
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ─── Flask App ───
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# ─── Servisler ───
db = Database()
db.connect()
db.create_tables()
db.seed_leagues_and_seasons()

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

# ─── Global State for Async Updates ───
_weekly_update_lock = threading.Lock()
_is_weekly_updating = False
_last_weekly_update = 0
_weekly_update_start_time = 0



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

@app.route("/api/sync/manual")
def api_sync_manual():
    """ESPN üzerinden manuel senkronizasyon tetikler."""
    from sync_recent_espn import sync_gap
    try:
        # Arka planda çalıştır
        thread = threading.Thread(target=sync_gap)
        thread.start()
        return jsonify({"status": "success", "message": "Senkronizasyon arka planda başlatıldı. sync_progress.log dosyasını kontrol edin."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

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
        # Sadece gelecekteki maçları filtrele
        now_str = datetime.now().strftime("%Y-%m-%d")
        upcoming = []
        for p in stats["history"]:
            if p["match_date"] >= now_str:
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
                        except:
                            p[col] = {}
                    elif p.get(col) is None:
                        p[col] = {}
                upcoming.append(p)
        
        # 2. Eğer veri yoksa veya eskiyse (1 saat) arka planda güncelleme başlat
        should_update = len(upcoming) == 0 or (time.time() - _last_weekly_update > 3600)
        
        if should_update and not _is_weekly_updating:
            def background_update():
                global _is_weekly_updating, _last_weekly_update
                with _weekly_update_lock:
                    if _is_weekly_updating: return
                    _is_weekly_updating = True
                
                try:
                    logger.info("📡 Arka planda haftalık bülten güncelleniyor...")
                    weekly_scraper.get_weekly_predictions()
                    _last_weekly_update = time.time()
                    logger.info("✅ Arka plan güncellemesi tamamlandı.")
                except Exception as e:
                    logger.error(f"Arka plan güncelleme hatası: {e}")
                finally:
                    with _weekly_update_lock:
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
        return jsonify({"error": str(e)}), 500

@app.route("/api/weekly/refresh", methods=["POST"])
def api_weekly_refresh():
    """Haftalık bülteni ve analizleri manuel olarak tetikler."""
    global _is_weekly_updating, _last_weekly_update, _weekly_update_start_time
    
    with _weekly_update_lock:
        now = time.time()
        # Eğer 15 dakikadan uzun sürdüyse kilidi sıfırla (Çökme vb. durumu için)
        if _is_weekly_updating and (now - _weekly_update_start_time > 900):
            logger.warning("⚠️ Weekly update lock stuck (15min timeout), resetting...")
            _is_weekly_updating = False
            
        if _is_weekly_updating:
            return jsonify({"ok": False, "message": "Güncelleme zaten devam ediyor."}), 400
    
    def background_refresh():
        global _is_weekly_updating, _last_weekly_update, _weekly_update_start_time
        with _weekly_update_lock:
            _is_weekly_updating = True
            _weekly_update_start_time = time.time()
        try:
            logger.info("🚀 [MANUEL TETİK] Otonom analiz başlatıldı...")
            weekly_scraper.get_weekly_predictions()
            _last_weekly_update = time.time()
            logger.info("✅ [MANUEL TETİK] Analiz tamamlandı.")
            
            # ⚡ Biten maçların sonuçlarını otomatik çöz (Phase 14)
            logger.info("🏟️ Biten maçlar sonuçlandırılıyor...")
            weekly_scraper.resolve_pending_predictions()
            # ⚡ Eksik goals_market verilerini tamamla
            logger.info("🔧 Eksik Over 2.5 verileri tamamlanıyor...")
            db.backfill_missing_goals_market(ml_predictor=weekly_scraper.predictor)
        except Exception as e:
            logger.error(f"Refresh Hatası: {e}")
        finally:
            with _weekly_update_lock:
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
        return jsonify({"error": str(e)}), 500


# ─── Model Yönetimi (Self-Learning) ───

@app.route("/api/model/train", methods=["POST"])
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
        return jsonify({"error": str(e)}), 500


# ─── AutoResearch API ───────────────────────────────────────────

@app.route("/api/autoresearch/start", methods=["POST"])
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
def api_ar_promote():
    """Champion deneyi aktif ML modeline promote eder."""
    def run_promote():
        auto_researcher.promote_champion()
    threading.Thread(target=run_promote, daemon=True).start()
    return jsonify({"ok": True, "message": "Champion modeli eğitiliyor. Bu birkaç dakika sürebilir."})


# ─── Veri İndirme ───

@app.route("/api/fetch", methods=["POST"])
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
            db.import_all_csvs()
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
    Günde 2 kere otomatik olarak veritabanını günceller, geçmiş maç sonuçlarını onarır (resolve)
    ve günün iddaa bültenini tarayıp yeni tahminler çıkarır. Hiçbir insan müdahalesi gerektirmez.
    """
    last_run_date = None
    runs_today = 0
    
    # Sunucu başlar başlamaz bir kez hızlı bir resolve çalıştır.
    try:
        logger.info("🔄 Uygulama başlangıcı: Bekleyen sonuçlar kontrol ediliyor...")
        weekly_scraper.resolve_pending_predictions()
    except:
        pass

    while True:
        try:
            now = datetime.now()
            
            # Yeni günde sayscı sıfırla
            if last_run_date != now.date():
                last_run_date = now.date()
                runs_today = 0
                
            # Günde iki kere: (örneğin sabah 09:xx ve akşam 19:xx -> maçlar bitince ve bülten çıkınca)
            is_morning_run = runs_today == 0 and now.hour == 9
            is_evening_run = runs_today == 1 and now.hour == 19
            
            if is_morning_run or is_evening_run:
                logger.info(f"⏰ [OTONOM YÖNETİM] Günlük Veri Güncelleme ve Doğrulama Rutini Başlıyor... ({now.strftime('%H:%M')})")
                
                # 1. Bekleyen tahminleri çözümle (Maçlar bittiyse başarı analizini günceller)
                logger.info("   -> Bekleyen sonuçlar doğrulanıyor...")
                try:
                    weekly_scraper.resolve_pending_predictions()
                except Exception as e:
                    logger.error(f"   ❌ Resolve hatası: {e}")
                
                # 2. Football-Data.co.uk sitesindeki en güncel CSV maç sonuçlarını çek / aktar
                logger.info("   -> En güncel istatistik verileri ve sonuçlar indiriliyor...")
                try:
                    fetcher.fetch_all(only_latest_season=True)
                    db.import_all_csvs()
                except Exception as e:
                    logger.error(f"   X Veri Cekme & Ictarma hatasi: {e}")

                # 2b. Eksik takım verilerini alternatif kaynaklardan tamamla
                logger.info("   -> Eksik takim verileri kontrol ediliyor...")
                try:
                    from auto_updater import run_auto_update
                    run_auto_update(db, import_to_db=True)
                except Exception as e:
                    logger.error(f"   X AutoUpdater hatasi: {e}")

                # 2c. Harici kaynaklar: Understat xG + ClubElo
                logger.info("   -> Harici kaynaklar (xG, ELO) senkronize ediliyor...")
                try:
                    from external_data_integrator import run_external_data_sync
                    run_external_data_sync(db)
                except Exception as e:
                    logger.error(f"   X Harici veri hatasi: {e}")

                
                # 3. Haftalık iddaa bültenindeki maçları çekip ML & İstatistik ile tahmin yaptır
                logger.info("   -> Haftalık iddaa bülteni çekiliyor ve yapay zeka tahminleri üretiliyor...")
                try:
                    weekly_scraper.get_weekly_predictions()
                except Exception as e:
                    logger.error(f"   ❌ Haftalık Bülten Scraper hatası: {e}")
                    
                logger.info("✅ [OTONOM YÖNETİM] Rutin Görev Tamamlandı. Veriler, başarı skorları ve tahminler güncel!")
                runs_today += 1
                
        except Exception as e:
            logger.error(f"Otonom Updater Döngü Hatası: {e}")
            
        # 30 dakikada bir zamanı kontrol et
        time.sleep(1800)


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
        import threading
        threading.Thread(target=_autonomous_daily_updater, daemon=True).start()
    else:
        logger.info("💤 Arka plan hizmetleri devre dışı (ENABLE_BACKGROUND_TASKS=False).")
        
        # ⚡ Başlangıçta eksik Over 2.5 verilerini tamamla
        def _startup_backfill():
            import time
            time.sleep(5)  # App tamamen yüklensin
            try:
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
